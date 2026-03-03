
from infrastructure.db_manager import DatabaseManager

def list_tomehub_tables():
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT table_name FROM user_tables WHERE table_name LIKE 'TOMEHUB_%' ORDER BY table_name")
                tables = [row[0] for row in cursor.fetchall()]
                print(f"Found {len(tables)} TOMEHUB tables:")
                for table in tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    print(f"- {table}: {count} rows")
                    
                    # Also list columns for each table to be sure
                    cursor.execute(f"SELECT column_name, data_type FROM user_tab_columns WHERE table_name = '{table}' ORDER BY column_id")
                    cols = cursor.fetchall()
                    col_str = ", ".join([f"{c[0]} ({c[1]})" for c in cols])
                    print(f"  Cols: {col_str}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_tomehub_tables()
