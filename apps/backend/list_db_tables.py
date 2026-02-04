
from infrastructure.db_manager import DatabaseManager

def list_tables():
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT table_name FROM user_tables ORDER BY table_name")
                for row in cursor.fetchall():
                    print(row[0])
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_tables()
