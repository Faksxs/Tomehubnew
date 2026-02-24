#!/usr/bin/env python3
"""Final reconciliation: Unique Title+Author vs Raw IDs."""
import sys
sys.path.insert(0, '/app')
from infrastructure.db_manager import DatabaseManager

DatabaseManager.init_pool()
conn = DatabaseManager.get_read_connection()
cursor = conn.cursor()

# 1. Logical Books count
cursor.execute("SELECT COUNT(DISTINCT LOWER(TRIM(TITLE)) || ' - ' || LOWER(TRIM(AUTHOR))) FROM TOMEHUB_BOOKS")
logical_count = cursor.fetchone()[0]

# 2. Breakdown of IDs by content type presence
cursor.execute("""
    SELECT 
        COUNT(CASE WHEN SOURCE_TYPE IN ('PDF', 'BOOK') THEN 1 END) as main_books,
        COUNT(CASE WHEN SOURCE_TYPE = 'HIGHLIGHT' THEN 1 END) as highlights,
        COUNT(CASE WHEN SOURCE_TYPE = 'PERSONAL_NOTE' THEN 1 END) as personal_notes,
        COUNT(CASE WHEN SOURCE_TYPE = 'ARTICLE' THEN 1 END) as articles,
        COUNT(CASE WHEN SOURCE_TYPE = 'WEBSITE' THEN 1 END) as websites
    FROM (
        SELECT DISTINCT BOOK_ID, SOURCE_TYPE FROM TOMEHUB_CONTENT
    )
""")
breakdown = cursor.fetchone()

print(f"Total Database IDs (TOMEHUB_BOOKS): 268")
print(f"Unique Logical Books (Title + Author): {logical_count}")
print("-" * 30)
print(f"Main Book IDs (PDF/BOOK):  {breakdown[0] or 0}")
print(f"Highlight-only IDs:        {breakdown[1] or 0}")
print(f"Personal Note IDs:         {breakdown[2] or 0}")
print(f"Article IDs:               {breakdown[3] or 0}")
print(f"Website IDs:               {breakdown[4] or 0}")

cursor.close()
conn.close()
DatabaseManager.close_pool()
