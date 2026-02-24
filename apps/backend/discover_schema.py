from infrastructure.db_manager import DatabaseManager

def discover_schema():
    try:
        conn = DatabaseManager.get_read_connection()
        cur = conn.cursor()
        
        tables = ['TOMEHUB_LIBRARY_ITEMS', 'TOMEHUB_CONTENT_V2']
        for table in tables:
            print(f"\n--- Columns for {table} ---")
            cur.execute(f"SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = '{table}'")
            cols = [r[0] for r in cur.fetchall()]
            for c in cols:
                print(c)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    discover_schema()
