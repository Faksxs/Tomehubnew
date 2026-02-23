#!/usr/bin/env python3
"""Find orphaned highlights (no matching TOMEHUB_BOOKS entry)."""
import sys
sys.path.insert(0, '/app')
from infrastructure.db_manager import DatabaseManager

DatabaseManager.init_pool()
conn = DatabaseManager.get_read_connection()
cursor = conn.cursor()

# Find highlights with 'kader' that DON'T join to TOMEHUB_BOOKS
cursor.execute("""
    SELECT c.TITLE, c.SOURCE_TYPE, c.BOOK_ID,
           SUBSTR(c.CONTENT_CHUNK, 1, 100) AS snippet
    FROM TOMEHUB_CONTENT c
    WHERE c.SOURCE_TYPE IN ('HIGHLIGHT', 'INSIGHT')
    AND LOWER(c.CONTENT_CHUNK) LIKE '%kader%'
    AND c.BOOK_ID NOT IN (SELECT ID FROM TOMEHUB_BOOKS)
    ORDER BY c.TITLE
""")
orphans = cursor.fetchall()
print(f"\n=== ORPHANED highlights with 'kader' (no TOMEHUB_BOOKS entry): {len(orphans)} ===")
for r in orphans:
    print(f"  [{r[1]}] title={r[0]} book_id={r[2]}")
    print(f"    snippet: {str(r[3])[:100]}")

# Also check: how many total orphaned highlights exist?
cursor.execute("""
    SELECT COUNT(*) FROM TOMEHUB_CONTENT c
    WHERE c.SOURCE_TYPE IN ('HIGHLIGHT', 'INSIGHT')
    AND c.BOOK_ID NOT IN (SELECT ID FROM TOMEHUB_BOOKS)
""")
total_orphans = cursor.fetchone()[0]
print(f"\n=== TOTAL orphaned highlights (all books): {total_orphans} ===")

# List all unique book_ids that are orphaned
cursor.execute("""
    SELECT c.BOOK_ID, c.TITLE, COUNT(*) as cnt
    FROM TOMEHUB_CONTENT c
    WHERE c.SOURCE_TYPE IN ('HIGHLIGHT', 'INSIGHT')
    AND c.BOOK_ID NOT IN (SELECT ID FROM TOMEHUB_BOOKS)
    GROUP BY c.BOOK_ID, c.TITLE
    ORDER BY cnt DESC
""")
orphan_books = cursor.fetchall()
print(f"\n=== Orphaned book_ids ({len(orphan_books)} unique) ===")
for r in orphan_books:
    print(f"  book_id={r[0]} title={r[1]} highlights={r[2]}")

# Also check Layer 2 search path — what does the search API actually query?
cursor.execute("""
    SELECT COUNT(*) FROM TOMEHUB_BOOKS
""")
book_count = cursor.fetchone()[0]
print(f"\n=== TOMEHUB_BOOKS total: {book_count} ===")

cursor.close()
conn.close()
DatabaseManager.close_pool()
