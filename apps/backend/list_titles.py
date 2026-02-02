
from infrastructure.db_manager import DatabaseManager

def list_all_books():
    DatabaseManager.init_pool()
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT title, categories FROM TOMEHUB_CONTENT")
            rows = cursor.fetchall()
            with open("all_titles_utf8.txt", "w", encoding="utf-8") as f:
                f.write(f"Found {len(rows)} unique records.\n")
                for title, categories in rows:
                    f.write(f"Title: '{title}' | Categories: '{categories}'\n")
            print(f"Results written to all_titles_utf8.txt")

if __name__ == "__main__":
    list_all_books()
