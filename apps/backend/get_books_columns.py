
from infrastructure.db_manager import DatabaseManager

def get_columns():
    try:
        conn = DatabaseManager.get_read_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM TOMEHUB_BOOKS WHERE ROWNUM = 1")
        print([col[0] for col in cursor.description])
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_columns()
