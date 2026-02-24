import os
from infrastructure.db_manager import DatabaseManager

def main():
    try:
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()

        output = []

        # Total counts
        cursor.execute("SELECT COUNT(*) FROM TOMEHUB_BOOKS")
        total_books = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM TOMEHUB_LIBRARY_ITEMS WHERE ITEM_TYPE = 'BOOK'")
        total_items = cursor.fetchone()[0]
        
        output.append(f"Total entries in TOMEHUB_BOOKS: {total_books}")
        output.append(f"Total entries in TOMEHUB_LIBRARY_ITEMS: {total_items}")

        # Find missing ones by ID mapping (BOOK_ID -> ITEM_ID)
        query = """
        SELECT b.ID, b.TITLE, b.FIREBASE_UID 
        FROM TOMEHUB_BOOKS b 
        LEFT JOIN TOMEHUB_LIBRARY_ITEMS li ON b.ID = li.ITEM_ID 
        WHERE li.ITEM_ID IS NULL
        """
        cursor.execute(query)
        missing_books = cursor.fetchall()
        
        if missing_books:
            output.append(f"\nFound {len(missing_books)} books in TOMEHUB_BOOKS that are NOT in TOMEHUB_LIBRARY_ITEMS:")
            for i, row in enumerate(missing_books[:20]):
                output.append(f" - ID: {row[0]}, TITLE: {row[1]}, UID: {row[2]}")
            if len(missing_books) > 20:
                output.append(f" ... and {len(missing_books) - 20} more.")
        else:
            output.append("\nExcellent! All books from TOMEHUB_BOOKS exist in TOMEHUB_LIBRARY_ITEMS.")

        cursor.close()
        conn.close()

        with open('clean_compare_output.txt', 'w', encoding='utf-8') as f:
            f.write("\n".join(output))

        print("Done writing to clean_compare_output.txt")
    except Exception as e:
        print(f"Main Error: {e}")

if __name__ == "__main__":
    main()
