import os
import sys

# Add apps/backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

def final_verify():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # Get all records for 'Klasik Sosyoloji'
                cursor.execute('''
                    SELECT book_id, count(*) 
                    FROM TOMEHUB_CONTENT 
                    WHERE title LIKE '%Klasik Sosyoloji%' 
                    GROUP BY book_id
                ''')
                content_results = cursor.fetchall()
                print("--- TOMEHUB_CONTENT ---")
                for res in content_results:
                    print(f"Book ID: {res[0]}, Chunks: {res[1]}")

                # Get status for these IDs
                cursor.execute('''
                    SELECT book_id, status, source_file_name, updated_at 
                    FROM TOMEHUB_INGESTED_FILES 
                    WHERE source_file_name LIKE '%Klasik%' 
                    OR book_id IN (SELECT book_id FROM TOMEHUB_CONTENT WHERE title LIKE '%Klasik Sosyoloji%')
                ''')
                status_results = cursor.fetchall()
                print("\n--- TOMEHUB_INGESTED_FILES ---")
                for res in status_results:
                    print(f"Book ID: {res[0]}, Status: {res[1]}, File: {res[2]}, Updated: {res[3]}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == '__main__':
    final_verify()
