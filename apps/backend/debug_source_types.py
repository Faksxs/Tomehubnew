from infrastructure.db_manager import DatabaseManager

DatabaseManager.init_pool()
conn = DatabaseManager.get_connection()
cur = conn.cursor()

uid = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'

# Check source types
cur.execute(f"SELECT source_type, COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid='{uid}' GROUP BY source_type")
print("\n=== SOURCE TYPES ===")
for row in cur.fetchall():
    print(f"{row[0]}: {row[1]} items")

# Check titles with "- Self" suffix
cur.execute(f"SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid='{uid}' AND title LIKE '% - Self'")
self_count = cur.fetchone()[0]
print(f"\n=== TITLES WITH '- Self' ===")
print(f"Count: {self_count}")

# Check what should be personal notes (NOTES OR PDF with - Self)
cur.execute(f"""
    SELECT COUNT(*) FROM TOMEHUB_CONTENT 
    WHERE firebase_uid='{uid}' 
    AND (source_type = 'NOTES' OR (source_type = 'PDF' AND title LIKE '% - Self'))
""")
personal_count = cur.fetchone()[0]
print(f"\n=== PERSONAL NOTES (Filter Match) ===")
print(f"Count: {personal_count}")

# Show sample personal notes
cur.execute(f"""
    SELECT id, title, source_type FROM TOMEHUB_CONTENT 
    WHERE firebase_uid='{uid}' 
    AND (source_type = 'NOTES' OR (source_type = 'PDF' AND title LIKE '% - Self'))
    ORDER BY ROWNUM FETCH FIRST 10 ROWS ONLY
""")
print(f"\n=== SAMPLE PERSONAL NOTES ===")
for row in cur.fetchall():
    print(f"ID: {row[0]}, Title: {row[1]}, Type: {row[2]}")

conn.close()
