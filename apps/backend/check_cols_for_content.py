
from infrastructure.db_manager import DatabaseManager

def list_cols(table_name):
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT column_name, data_type FROM user_tab_columns WHERE table_name = '{table_name}' ORDER BY column_id")
                cols = cursor.fetchall()
                print(f"Columns for {table_name}:")
                for c in cols:
                    print(f"  - {c[0]} ({c[1]})")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_cols("TOMEHUB_CONTENT_V2")
    list_cols("TOMEHUB_CONTENT_ARCHIVED")
