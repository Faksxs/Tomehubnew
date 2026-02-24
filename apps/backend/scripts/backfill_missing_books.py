#!/usr/bin/env python3
"""
Backfill missing TOMEHUB_BOOKS entries from orphaned TOMEHUB_CONTENT rows.

Safety: INSERT-ONLY. No DELETE or UPDATE on existing data.
v2: Fixed ORA-00923 by using simple INSERT with existence check.
"""
import sys
sys.path.insert(0, '/app')
from infrastructure.db_manager import DatabaseManager

DatabaseManager.init_pool()

# Step 1: Find all orphaned book_ids with their metadata
conn = DatabaseManager.get_read_connection()
cursor = conn.cursor()

cursor.execute("""
    SELECT c.BOOK_ID, c.TITLE, c.FIREBASE_UID, COUNT(*) as highlight_count
    FROM TOMEHUB_CONTENT c
    WHERE c.SOURCE_TYPE IN ('HIGHLIGHT', 'INSIGHT')
    AND NOT EXISTS (SELECT 1 FROM TOMEHUB_BOOKS b WHERE b.ID = c.BOOK_ID)
    GROUP BY c.BOOK_ID, c.TITLE, c.FIREBASE_UID
    ORDER BY COUNT(*) DESC
""")
orphans = cursor.fetchall()
cursor.close()
conn.close()

print(f"\n=== Found {len(orphans)} orphaned book entries to backfill ===")
if not orphans:
    print("Nothing to do!")
    DatabaseManager.close_pool()
    sys.exit(0)

# Step 2: Parse title and author from the "Title - Author" format
def parse_title_author(combined_title):
    if not combined_title:
        return ("Unknown", "Unknown")
    clean = combined_title.strip()
    for suffix in (" (Highlight)", " (Insight)", " (highlight)", " (insight)"):
        if clean.endswith(suffix):
            clean = clean[:-len(suffix)].strip()
    parts = clean.rsplit(" - ", 1)
    if len(parts) == 2:
        return (parts[0].strip(), parts[1].strip())
    return (clean, "Unknown")

# Step 3: Insert missing books using simple INSERT with NOT EXISTS guard
print("\n--- Inserting missing TOMEHUB_BOOKS entries ---")
write_conn = DatabaseManager.get_write_connection()
write_cursor = write_conn.cursor()

inserted = 0
errors = 0

for orphan in orphans:
    book_id = orphan[0]
    raw_title = orphan[1]
    firebase_uid = orphan[2]
    highlight_count = orphan[3]

    title, author = parse_title_author(raw_title)

    try:
        write_cursor.execute("""
            INSERT INTO TOMEHUB_BOOKS (ID, TITLE, AUTHOR, FIREBASE_UID, CREATED_AT)
            SELECT :p_id, :p_title, :p_author, :p_uid, CURRENT_TIMESTAMP
            FROM DUAL
            WHERE NOT EXISTS (SELECT 1 FROM TOMEHUB_BOOKS WHERE ID = :p_id2)
        """, {
            "p_id": book_id,
            "p_title": title,
            "p_author": author,
            "p_uid": firebase_uid,
            "p_id2": book_id,
        })
        if write_cursor.rowcount > 0:
            inserted += 1
            print(f"  [OK] {title} by {author} ({highlight_count} highlights)")
        else:
            print(f"  [SKIP] {title} already exists")
    except Exception as e:
        errors += 1
        print(f"  [ERR] {title}: {e}")

write_conn.commit()
write_cursor.close()
write_conn.close()

print(f"\n=== Backfill Complete ===")
print(f"  Inserted: {inserted}")
print(f"  Errors: {errors}")

# Step 4: Verify
print("\n--- Verification ---")
verify_conn = DatabaseManager.get_read_connection()
verify_cursor = verify_conn.cursor()

verify_cursor.execute("SELECT COUNT(*) FROM TOMEHUB_BOOKS")
total_books = verify_cursor.fetchone()[0]

verify_cursor.execute("""
    SELECT COUNT(*) FROM TOMEHUB_CONTENT c
    WHERE c.SOURCE_TYPE IN ('HIGHLIGHT', 'INSIGHT')
    AND NOT EXISTS (SELECT 1 FROM TOMEHUB_BOOKS b WHERE b.ID = c.BOOK_ID)
""")
remaining_orphans = verify_cursor.fetchone()[0]

verify_cursor.execute("""
    SELECT b.TITLE, c.SOURCE_TYPE, SUBSTR(c.CONTENT_CHUNK, 1, 80)
    FROM TOMEHUB_CONTENT c
    JOIN TOMEHUB_BOOKS b ON c.BOOK_ID = b.ID AND c.FIREBASE_UID = b.FIREBASE_UID
    WHERE c.SOURCE_TYPE IN ('HIGHLIGHT', 'INSIGHT')
    AND LOWER(c.CONTENT_CHUNK) LIKE '%kader%'
    ORDER BY b.TITLE
""")
kader_results = verify_cursor.fetchall()

print(f"  TOMEHUB_BOOKS total: {total_books}")
print(f"  Remaining orphans: {remaining_orphans}")
print(f"  'kader' highlights now joinable: {len(kader_results)}")
for r in kader_results:
    print(f"    [{r[1]}] {r[0]}: {str(r[2])[:70]}")

verify_cursor.close()
verify_conn.close()
DatabaseManager.close_pool()
