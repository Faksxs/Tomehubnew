#!/usr/bin/env python3
"""List all unique Title | Author pairs."""
import sys
sys.path.insert(0, '/app')
from infrastructure.db_manager import DatabaseManager

DatabaseManager.init_pool()
conn = DatabaseManager.get_read_connection()
cursor = conn.cursor()

cursor.execute("SELECT DISTINCT TITLE, AUTHOR FROM TOMEHUB_BOOKS ORDER BY TITLE")
rows = cursor.fetchall()
for r in rows:
    print(f"{r[0]} | {r[1]}")

cursor.close()
conn.close()
DatabaseManager.close_pool()
