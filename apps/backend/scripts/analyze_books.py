#!/usr/bin/env python3
"""Analyze TOMEHUB_BOOKS for duplicates and categorize by source type."""
import sys
sys.path.insert(0, '/app')
from infrastructure.db_manager import DatabaseManager

DatabaseManager.init_pool()
conn = DatabaseManager.get_read_connection()
cursor = conn.cursor()

print("=" * 60)
print("BOOK DUPLICATE & CATEGORY ANALYSIS")
print("=" * 60)

# 1. Check for logically duplicate books (same title and author)
print("\n[1] Logical Duplicates (Same Title + Author, Multiple IDs):")
cursor.execute("""
    SELECT TITLE, AUTHOR, COUNT(*) as id_count, LISTAGG(SUBSTR(ID, 1, 8), ', ') 
    FROM TOMEHUB_BOOKS
    GROUP BY TITLE, AUTHOR
    HAVING COUNT(*) > 1
    ORDER BY id_count DESC
""")
duplicates = cursor.fetchall()
if duplicates:
    print(f"    Found {len(duplicates)} logical groups with multiple IDs.")
    for d in duplicates[:15]:
        print(f"      - {d[0]} by {d[1]}: {d[2]} IDs ({d[3]}...)")
    if len(duplicates) > 15:
        print(f"      ... and {len(duplicates) - 15} more groups.")
else:
    print("    No exact Title+Author duplicates found.")

# 2. Check source type distribution for all books
print("\n[2] Source Type distribution for 268 IDs:")
cursor.execute("""
    SELECT c.SOURCE_TYPE, COUNT(DISTINCT c.BOOK_ID)
    FROM TOMEHUB_CONTENT c
    GROUP BY c.SOURCE_TYPE
    ORDER BY COUNT(DISTINCT c.BOOK_ID) DESC
""")
types = cursor.fetchall()
for t in types:
    print(f"    {t[0]}: {t[1]} unique book_ids")

# 3. Check for "Title - Author" vs "Title" mismatches
print("\n[3] Potential Title Mismatches (Partial matches):")
cursor.execute("""
    SELECT t1.TITLE, t1.AUTHOR, t2.TITLE, t2.AUTHOR
    FROM TOMEHUB_BOOKS t1
    JOIN TOMEHUB_BOOKS t2 ON t1.ID < t2.ID
    WHERE (LOWER(t1.TITLE) LIKE '%' || LOWER(t2.TITLE) || '%' OR LOWER(t2.TITLE) || '%' LIKE '%' || LOWER(t1.TITLE) || '%')
    AND t1.TITLE != t2.TITLE
    AND ROWNUM <= 10
""")
mismatches = cursor.fetchall()
for m in mismatches:
    print(f"    '{m[0]}' vs. '{m[2]}'")

# 4. Filter: How many "True Books" (PDF/HIGHLIGHT) vs "Other" (WEBSITE/ARTICLE)
cursor.execute("""
    SELECT COUNT(DISTINCT BOOK_ID) 
    FROM TOMEHUB_CONTENT 
    WHERE SOURCE_TYPE IN ('PDF', 'HIGHLIGHT', 'INSIGHT', 'BOOK')
""")
true_books = cursor.fetchone()[0]
print(f"\n[4] Total unique book_ids for 'True' Book types: {true_books}")

cursor.close()
conn.close()
DatabaseManager.close_pool()
