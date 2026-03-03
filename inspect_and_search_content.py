
import oracledb
import json
import os
import sys
from dotenv import load_dotenv

# Add apps/backend to path to reuse infrastructure if possible
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

load_dotenv(os.path.join(os.getcwd(), 'apps', 'backend', '.env'))

def get_db_connection():
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    dsn = os.getenv("DB_DSN")
    
    if not all([user, password, dsn]):
        # Try default local config
        user = "TOMEHUB"
        password = "Tomehub123"
        dsn = "localhost:1521/XEPDB1"
        
    return oracledb.connect(user=user, password=password, dsn=dsn)

def inspect_schemas():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    tables = ['TOMEHUB_CONTENT_V2', 'TOMEHUB_CONTENT_ARCHIVED']
    schemas = {}
    
    for table in tables:
        cursor.execute(f"SELECT column_name, data_type FROM user_tab_columns WHERE table_name = '{table}'")
        schemas[table] = [row for row in cursor.fetchall()]
    
    with open("content_schemas.json", "w", encoding="utf-8") as f:
        json.dump(schemas, f, indent=2)
        
    # Also search for the book ID in these tables specifically
    target_id = "1763947192884s1obi7m9k"
    found_highlights = []
    
    for table in tables:
        # Check if BOOK_ID or ITEM_ID exists as column
        cursor.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table}'")
        cols = [r[0] for r in cursor.fetchall()]
        
        search_col = None
        if 'BOOK_ID' in cols:
            search_col = 'BOOK_ID'
        elif 'ITEM_ID' in cols:
            search_col = 'ITEM_ID'
            
        if search_col:
            print(f"Searching {table} using {search_col}...")
            cursor.execute(f"SELECT * FROM {table} WHERE {search_col} = :tid", tid=target_id)
            # Fetch all and get column names
            columns = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            for r in rows:
                row_dict = dict(zip(columns, r))
                # Only keep non-blob/non-huge fields for the summary
                cleaned_row = {}
                for k, v in row_dict.items():
                    if k == 'VEC_EMBEDDING': continue # skip large binary
                    if hasattr(v, 'read'):
                        cleaned_row[k] = v.read()[:500] # preview LOBs
                    else:
                        cleaned_row[k] = str(v)
                found_highlights.append({"table": table, "data": cleaned_row})

    with open("found_book_content.json", "w", encoding="utf-8") as f:
        json.dump(found_highlights, f, indent=2, ensure_ascii=False)

    cursor.close()
    conn.close()
    print("Done. Results in content_schemas.json and found_book_content.json")

if __name__ == "__main__":
    inspect_schemas()
