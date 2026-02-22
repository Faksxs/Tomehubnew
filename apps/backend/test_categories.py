import os
import sys

# Add the app path to sys.path so we can import from infrastructure
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

def test():
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cursor:
            # Look for Bir Havva Kızı and Esir Şehrin İnsanları
            titles = ["Bir Havva Kızı%", "Esir Şehrin İnsanları%"]
            for title in titles:
                print(f"--- Checking {title} ---")
                cursor.execute("""
                    SELECT c.id, c.title
                    FROM TOMEHUB_CONTENT c
                    WHERE c.title LIKE :p_title
                    FETCH FIRST 5 ROWS ONLY
                """, {"p_title": title})
                
                rows = cursor.fetchall()
                if not rows:
                    print(f"No content found for {title}")
                
                for row in rows:
                    content_id = row[0]
                    content_title = row[1]
                    print(f"Found ID: {content_id}, Title: {content_title}")
                    
                    cursor.execute("""
                        SELECT category_norm
                        FROM TOMEHUB_CONTENT_CATEGORIES
                        WHERE content_id = :p_id
                    """, {"p_id": content_id})
                    
                    cat_rows = cursor.fetchall()
                    categories = [r[0] for r in cat_rows]
                    print(f"  Categories: {categories}")

if __name__ == "__main__":
    test()
