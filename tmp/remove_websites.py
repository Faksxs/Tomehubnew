import sqlite3
import os

db_path = r"C:\Users\aksoy\Desktop\yeni tomehub\apps\backend\tomehub.db"
# Fallback if DB is in parent dir
if not os.path.exists(db_path):
    db_path = r"C:\Users\aksoy\Desktop\yeni tomehub\tomehub.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("DELETE FROM books WHERE item_type = 'WEBSITE'")
    print(f"Deleted item_type WEBSITE: {cursor.rowcount}")
except sqlite3.OperationalError as e:
    print(f"Error 1: {e}")

try:
    cursor.execute("DELETE FROM books WHERE source_type = 'WEBSITE'")
    print(f"Deleted source_type WEBSITE: {cursor.rowcount}")
except sqlite3.OperationalError as e:
    print(f"Error 2: {e}")

conn.commit()
conn.close()
