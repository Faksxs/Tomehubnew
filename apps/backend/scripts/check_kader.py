#!/usr/bin/env python3
"""Diagnostic: Find all highlights containing 'kader' in Oracle DB."""
import sys
sys.path.insert(0, '/app')
from infrastructure.db_manager import DatabaseManager

DatabaseManager.init_pool()
conn = DatabaseManager.get_read_connection()
cursor = conn.cursor()

# Search ALL content types for 'kader'
cursor.execute("""
    SELECT b.TITLE, c.SOURCE_TYPE, c.BOOK_ID,
           DBMS_LOB.SUBSTR(c.CONTENT, 120, 1) AS snippet
    FROM TOMEHUB_CONTENT c
    JOIN TOMEHUB_BOOKS b ON c.BOOK_ID = b.ID AND c.FIREBASE_UID = b.FIREBASE_UID
    WHERE LOWER(DBMS_LOB.SUBSTR(c.CONTENT, 4000, 1)) LIKE '%kader%'
    ORDER BY c.SOURCE_TYPE, b.TITLE
""")
rows = cursor.fetchall()

print(f"\n=== ALL content with 'kader': {len(rows)} rows ===")
by_type = {}
for r in rows:
    t = r[1]
    by_type.setdefault(t, []).append(r)

for source_type, items in sorted(by_type.items()):
    print(f"\n--- {source_type} ({len(items)}) ---")
    for r in items:
        print(f"  [{r[2][:8]}] {r[0]}: {str(r[3])[:100]}")

# Now check specifically HIGHLIGHT and INSIGHT
cursor.execute("""
    SELECT COUNT(*) FROM TOMEHUB_CONTENT
    WHERE SOURCE_TYPE IN ('HIGHLIGHT', 'INSIGHT')
    AND LOWER(DBMS_LOB.SUBSTR(CONTENT, 4000, 1)) LIKE '%kader%'
""")
hl_count = cursor.fetchone()[0]
print(f"\n=== HIGHLIGHT+INSIGHT with 'kader': {hl_count} ===")

# Check total highlights per book
cursor.execute("""
    SELECT b.TITLE, COUNT(*) as cnt
    FROM TOMEHUB_CONTENT c
    JOIN TOMEHUB_BOOKS b ON c.BOOK_ID = b.ID AND c.FIREBASE_UID = b.FIREBASE_UID
    WHERE c.SOURCE_TYPE IN ('HIGHLIGHT', 'INSIGHT')
    GROUP BY b.TITLE
    ORDER BY cnt DESC
""")
rows2 = cursor.fetchall()
print(f"\n=== Total highlights per book ===")
total = 0
for r in rows2:
    print(f"  {r[0]}: {r[1]}")
    total += r[1]
print(f"  GRAND TOTAL: {total}")

cursor.close()
conn.close()
DatabaseManager.close_pool()
