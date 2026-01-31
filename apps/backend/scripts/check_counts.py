# Check source types for user

import sys
sys.path.insert(0, '.')

from infrastructure.db_manager import DatabaseManager

DatabaseManager.init_pool()

uid = 'vpq1p0UzcCSLAh1d18WgZZWPBE63'

conn = DatabaseManager.get_connection()
cur = conn.cursor()

print("Content Source Types:")
cur.execute(f"SELECT source_type, COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = '{uid}' GROUP BY source_type")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

conn.close()
