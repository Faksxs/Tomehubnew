import os
from infrastructure.db_manager import DatabaseManager

def main():
    try:
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()

        # 1. Add TOTAL_CHUNKS to TOMEHUB_LIBRARY_ITEMS
        print("--- 1. Adding TOTAL_CHUNKS to TOMEHUB_LIBRARY_ITEMS ---")
        try:
            cursor.execute("ALTER TABLE TOMEHUB_LIBRARY_ITEMS ADD (TOTAL_CHUNKS NUMBER DEFAULT 0)")
            conn.commit()
            print("Successfully added TOTAL_CHUNKS column.")
        except Exception as e:
            if "ORA-01430" in str(e): # column being added already exists
                print("TOTAL_CHUNKS column already exists.")
            else:
                print(f"Error adding column: {e}")

        # 2. Compare TOMEHUB_BOOKS vs TOMEHUB_LIBRARY_ITEMS
        print("\n--- 2. Comparing TOMEHUB_BOOKS and TOMEHUB_LIBRARY_ITEMS ---")
        
        # Total counts
        cursor.execute("SELECT COUNT(*) FROM TOMEHUB_BOOKS")
        total_books = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM TOMEHUB_LIBRARY_ITEMS WHERE ITEM_TYPE = 'BOOK'")
        total_items = cursor.fetchone()[0]
        
        print(f"Total entries in TOMEHUB_BOOKS: {total_books}")
        print(f"Total BOOK entries in TOMEHUB_LIBRARY_ITEMS: {total_items}")

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
            print(f"\nFound {len(missing_books)} books in TOMEHUB_BOOKS that are NOT in TOMEHUB_LIBRARY_ITEMS:")
            for i, row in enumerate(missing_books[:20]):
                print(f" - ID: {row[0]}, TITLE: {row[1]}, UID: {row[2]}")
            if len(missing_books) > 20:
                print(f" ... and {len(missing_books) - 20} more.")
        else:
            print("\nExcellent! All books from TOMEHUB_BOOKS exist in TOMEHUB_LIBRARY_ITEMS.")

        # Let's also sync TOTAL_CHUNKS from TOMEHUB_BOOKS to TOMEHUB_LIBRARY_ITEMS for the ones that exist
        if not missing_books or len(missing_books) < total_books:
            print("\n--- 3. Syncing TOTAL_CHUNKS from Legacy to New Table ---")
            sync_query = """
            MERGE INTO TOMEHUB_LIBRARY_ITEMS li
            USING TOMEHUB_BOOKS b
            ON (li.ITEM_ID = b.ID)
            WHEN MATCHED THEN
                UPDATE SET li.TOTAL_CHUNKS = b.TOTAL_CHUNKS
                WHERE (li.TOTAL_CHUNKS IS NULL OR li.TOTAL_CHUNKS = 0) AND b.TOTAL_CHUNKS > 0
            """
            cursor.execute(sync_query)
            conn.commit()
            print(f"Synced TOTAL_CHUNKS. Rows updated: {cursor.rowcount}")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Main Error: {e}")

if __name__ == "__main__":
    main()
