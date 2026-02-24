#!/usr/bin/env python3
"""
1. Discover actual Firestore collection structure
2. Fix remaining 129 orphan content rows (non-highlight)
3. Final verification

Safety: READ for Firestore, INSERT-ONLY for Oracle.
"""
import sys
sys.path.insert(0, '/app')

from infrastructure.db_manager import DatabaseManager
import firebase_admin
from firebase_admin import firestore

db = firestore.client()

# ── Step 1: Discover Firestore structure ──
print("=" * 60)
print("[1] FIRESTORE COLLECTION DISCOVERY")
print("=" * 60)

# Check root collections
root_collections = db.collections()
print("\nRoot collections:")
for col in root_collections:
    print(f"  - {col.id}")
    # Sample first 3 docs
    docs = col.limit(3).stream()
    for doc in docs:
        data = doc.to_dict() or {}
        keys = list(data.keys())[:5]
        print(f"      doc_id={doc.id}, fields={keys}")
        # Check subcollections
        subcols = doc.reference.collections()
        for sc in subcols:
            print(f"        subcol: {sc.id}")
            subdocs = sc.limit(2).stream()
            for sd in subdocs:
                sd_data = sd.to_dict() or {}
                sd_keys = list(sd_data.keys())[:5]
                print(f"          subdoc_id={sd.id}, fields={sd_keys}")

# ── Step 2: Fix remaining orphans ──
print("\n" + "=" * 60)
print("[2] FIXING REMAINING ORPHAN CONTENT ROWS")
print("=" * 60)

DatabaseManager.init_pool()
conn = DatabaseManager.get_read_connection()
cur = conn.cursor()

cur.execute("""
    SELECT c.BOOK_ID, c.TITLE, c.FIREBASE_UID, c.SOURCE_TYPE, COUNT(*) as cnt
    FROM TOMEHUB_CONTENT c
    WHERE NOT EXISTS (SELECT 1 FROM TOMEHUB_BOOKS b WHERE b.ID = c.BOOK_ID)
    GROUP BY c.BOOK_ID, c.TITLE, c.FIREBASE_UID, c.SOURCE_TYPE
    ORDER BY COUNT(*) DESC
""")
orphans = cur.fetchall()
cur.close()
conn.close()

print(f"\nFound {len(orphans)} orphan groups:")
for r in orphans:
    print(f"  [{r[3]}] book_id={r[0][:15]}..., title={r[1][:40]}, uid={r[2][:15]}, count={r[4]}")

# Parse title/author and insert missing books
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

# Collect unique book_ids to insert
seen = set()
to_insert = []
for r in orphans:
    book_id = r[0]
    if book_id not in seen:
        seen.add(book_id)
        title, author = parse_title_author(r[1])
        to_insert.append((book_id, title, author, r[2]))

print(f"\nInserting {len(to_insert)} missing book entries...")
write_conn = DatabaseManager.get_write_connection()
write_cur = write_conn.cursor()

inserted = 0
errors = 0
for book_id, title, author, uid in to_insert:
    try:
        write_cur.execute("""
            INSERT INTO TOMEHUB_BOOKS (ID, TITLE, AUTHOR, FIREBASE_UID, CREATED_AT)
            SELECT :p_id, :p_title, :p_author, :p_uid, CURRENT_TIMESTAMP
            FROM DUAL
            WHERE NOT EXISTS (SELECT 1 FROM TOMEHUB_BOOKS WHERE ID = :p_id2)
        """, {"p_id": book_id, "p_title": title, "p_author": author, "p_uid": uid, "p_id2": book_id})
        if write_cur.rowcount > 0:
            inserted += 1
            print(f"  [OK] {title} by {author}")
    except Exception as e:
        errors += 1
        print(f"  [ERR] {title}: {e}")

write_conn.commit()
write_cur.close()
write_conn.close()

print(f"\nInserted: {inserted}, Errors: {errors}")

# ── Step 3: Final verification ──
print("\n" + "=" * 60)
print("[3] FINAL VERIFICATION")
print("=" * 60)

verify_conn = DatabaseManager.get_read_connection()
verify_cur = verify_conn.cursor()

verify_cur.execute("SELECT COUNT(*) FROM TOMEHUB_BOOKS")
total_books = verify_cur.fetchone()[0]

verify_cur.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT")
total_content = verify_cur.fetchone()[0]

verify_cur.execute("""
    SELECT COUNT(*) FROM TOMEHUB_CONTENT c
    WHERE NOT EXISTS (SELECT 1 FROM TOMEHUB_BOOKS b WHERE b.ID = c.BOOK_ID)
""")
remaining_orphans = verify_cur.fetchone()[0]

verify_cur.execute("""
    SELECT SOURCE_TYPE, COUNT(*) FROM TOMEHUB_CONTENT GROUP BY SOURCE_TYPE ORDER BY COUNT(*) DESC
""")
breakdown = verify_cur.fetchall()

print(f"\n  TOMEHUB_BOOKS:     {total_books}")
print(f"  TOMEHUB_CONTENT:   {total_content}")
print(f"  Remaining orphans: {remaining_orphans}")
print(f"\n  Content breakdown:")
for r in breakdown:
    print(f"    {r[0]}: {r[1]}")

verify_cur.close()
verify_conn.close()
DatabaseManager.close_pool()
