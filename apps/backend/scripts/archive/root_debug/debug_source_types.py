
import os
import sys

# Add apps/backend to path to import infrastructure
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from infrastructure.db_manager import DatabaseManager

def check_source_types():
    print("Checking distinct source_type values in TOMEHUB_CONTENT...")
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT source_type, COUNT(*) 
                    FROM TOMEHUB_CONTENT 
                    GROUP BY source_type
                """)
                rows = cursor.fetchall()
                print(f"{'SOURCE_TYPE':<20} | {'COUNT'}")
                print("-" * 30)
                for r in rows:
                    print(f"{str(r[0]):<20} | {r[1]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_source_types()
