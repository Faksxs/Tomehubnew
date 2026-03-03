
import oracledb
from infrastructure.db_manager import DatabaseManager
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def search_more():
    results = {}
    try:
        conn = DatabaseManager.get_read_connection()
        cursor = conn.cursor()
        
        # 1. Search TOMEHUB_INGESTED_FILES
        print("Searching TOMEHUB_INGESTED_FILES...")
        table = "TOMEHUB_INGESTED_FILES"
        results[table] = []
        try:
            cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table}' ORDER BY column_id")
            cols = [c[0] for c in cursor.fetchall()]
            
            cursor.execute(f"SELECT * FROM {table} WHERE UPPER(FILE_NAME) LIKE '%AHMET%ARSLAN%' OR UPPER(FILE_NAME) LIKE '%ISLAM%FELSEFESI%'")
            rows = cursor.fetchall()
            for row in rows:
                results[table].append(dict(zip(cols, row)))
        except Exception as e:
            print(f"Error searching {table}: {e}")

        # 2. Search for ANY record with IS_DELETED=1 related to Ahmet Arslan
        print("Searching for deleted records...")
        tables = ["TOMEHUB_BOOKS", "TOMEHUB_LIBRARY_ITEMS"]
        for table in tables:
            try:
                cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table}' ORDER BY column_id")
                cols = [c[0] for c in cursor.fetchall()]
                
                query = f"SELECT * FROM {table} WHERE IS_DELETED = 1 AND (UPPER(TITLE) LIKE '%AHMET%ARSLAN%' OR UPPER(AUTHOR) LIKE '%AHMET%ARSLAN%' OR UPPER(TITLE) LIKE '%ISLAM%FELSEFESI%')"
                cursor.execute(query)
                rows = cursor.fetchall()
                for row in rows:
                    if f"DELETED_{table}" not in results: results[f"DELETED_{table}"] = []
                    results[f"DELETED_{table}"].append(dict(zip(cols, row)))
            except Exception as e:
                print(f"Error searching deleted in {table}: {e}")

        cursor.close()
        conn.close()
        
        with open("more_search_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print("Done. Results saved to more_search_results.json")
            
    except Exception as e:
        print(f"Global error: {e}")

if __name__ == "__main__":
    search_more()
