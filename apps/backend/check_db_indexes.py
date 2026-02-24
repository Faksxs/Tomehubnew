from infrastructure.db_manager import DatabaseManager
import os

def check_indexes():
    try:
        conn = DatabaseManager.get_read_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT table_name, index_name, column_name 
            FROM user_ind_columns 
            WHERE table_name IN ('TOMEHUB_LIBRARY_ITEMS', 'TOMEHUB_CONTENT_V2') 
            ORDER BY table_name, index_name, column_position
        """)
        rows = cur.fetchall()
        print("Table Name | Index Name | Column Name")
        print("-" * 60)
        for row in rows:
            print(f"{row[0]} | {row[1]} | {row[2]}")
        
        # Also check row count
        print("\nRow counts:")
        for table in ['TOMEHUB_LIBRARY_ITEMS', 'TOMEHUB_CONTENT_V2']:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"{table}: {count}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_indexes()
