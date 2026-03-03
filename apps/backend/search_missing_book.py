
import oracledb
from infrastructure.db_manager import DatabaseManager
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def search():
    results = {}
    try:
        conn = DatabaseManager.get_read_connection()
        cursor = conn.cursor()
        
        search_terms = ["%Ahmet Arslan%", "%İslam Felsefesi%"]
        
        tables = ["TOMEHUB_BOOKS", "TOMEHUB_LIBRARY_ITEMS", "TOMEHUB_CONTENT_V2"]
        
        for table in tables:
            print(f"Searching {table}...")
            results[table] = []
            try:
                # Get column names
                cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table}' ORDER BY column_id")
                cols = [c[0] for c in cursor.fetchall()]
                
                # Search for terms in all string columns
                cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table}' AND data_type IN ('VARCHAR2', 'NVARCHAR2', 'CLOB')")
                string_cols = [c[0] for c in cursor.fetchall()]
                
                if not string_cols:
                    continue
                    
                where_clauses = []
                params = {}
                for i, term in enumerate(search_terms):
                    for j, col in enumerate(string_cols):
                        param_name = f"p_{i}_{j}"
                        where_clauses.append(f"UPPER({col}) LIKE UPPER(:{param_name})")
                        params[param_name] = term
                
                query = f"SELECT * FROM {table} WHERE " + " OR ".join(where_clauses)
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                if rows:
                    for row in rows:
                        row_dict = {}
                        for idx, val in enumerate(row):
                            col_name = cols[idx]
                            if hasattr(val, 'read'): # CLOB
                                row_dict[col_name] = str(val.read())[:1000]
                            else:
                                row_dict[col_name] = str(val)
                        results[table].append(row_dict)
            except Exception as te:
                print(f"Error searching {table}: {te}")
                
        cursor.close()
        conn.close()
        
        with open("search_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("Done. Results saved to search_results.json")
            
    except Exception as e:
        print(f"Global error: {e}")

if __name__ == "__main__":
    search()
