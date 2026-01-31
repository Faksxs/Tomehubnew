import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Initialize DB pool first
from infrastructure.db_manager import DatabaseManager
DatabaseManager.init_pool()

try:
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Get all distinct source_type values
            cursor.execute("SELECT DISTINCT source_type FROM TOMEHUB_CONTENT ORDER BY source_type")
            print("=== All source_type values in database ===")
            for row in cursor.fetchall():
                print(f"  - {row[0]}")
            
            # Get count for each source_type
            cursor.execute("""
                SELECT source_type, COUNT(*) as count
                FROM TOMEHUB_CONTENT
                GROUP BY source_type
                ORDER BY source_type
            """)
            print("\n=== Count by source_type ===")
            for row in cursor.fetchall():
                print(f"  {row[0]}: {row[1]} items")
                
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    DatabaseManager.close_pool()
