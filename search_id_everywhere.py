
import cx_Oracle
import json
import os
from dotenv import load_dotenv

load_dotenv()

def search_id_everywhere():
    # Attempt to connect to Oracle
    # We'll use the environment variables if available
    user = os.getenv("DB_USER", "TOMEHUB")
    password = os.getenv("DB_PASSWORD", "Tomehub123")
    dsn = os.getenv("DB_DSN", "localhost:1521/XEPDB1")
    
    try:
        connection = cx_Oracle.connect(user=user, password=password, dsn=dsn)
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    cursor = connection.cursor()
    
    target_id = "1763947192884s1obi7m9k"
    
    # Get all TOMEHUB tables
    cursor.execute("SELECT table_name FROM user_tables WHERE table_name LIKE 'TOMEHUB_%'")
    tables = [row[0] for row in cursor.fetchall()]
    
    results = {}
    
    for table in tables:
        # Get columns
        cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table}'")
        columns = [row[0] for row in cursor.fetchall()]
        
        for col in columns:
            try:
                # Search for the target_id in each column
                # We use a simple query. If it fails (e.g. non-string column), we catch it.
                query = f"SELECT count(*) FROM {table} WHERE CAST({col} AS VARCHAR2(4000)) = :target_id"
                cursor.execute(query, target_id=target_id)
                count = cursor.fetchone()[0]
                if count > 0:
                    if table not in results:
                        results[table] = []
                    results[table].append(col)
                    print(f"Found {count} matches in {table}.{col}")
            except:
                pass

    with open("global_id_search_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    cursor.close()
    connection.close()

if __name__ == "__main__":
    search_id_everywhere()
