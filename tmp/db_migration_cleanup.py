from infrastructure.db_manager import DatabaseManager

def migrate():
    try:
        conn = DatabaseManager.get_write_connection()
        cur = conn.cursor()
        
        # 1. Standardize BOOK_CHUNK to EPUB
        cur.execute("UPDATE TOMEHUB_CONTENT_V2 SET CONTENT_TYPE = 'EPUB' WHERE CONTENT_TYPE = 'BOOK_CHUNK'")
        print(f"Updated {cur.rowcount} BOOK_CHUNK rows to EPUB")
        
        # 2. Clean up malformed types (specifically 'PDF F' or trailing spaces)
        # First, let's identify any PDF-like ones and make them 'PDF'
        cur.execute("UPDATE TOMEHUB_CONTENT_V2 SET CONTENT_TYPE = 'PDF' WHERE CONTENT_TYPE LIKE 'PDF%'")
        print(f"Sanitized {cur.rowcount} PDF-variant rows")
        
        # Just in case, trim everything
        cur.execute("UPDATE TOMEHUB_CONTENT_V2 SET CONTENT_TYPE = TRIM(CONTENT_TYPE)")
        print(f"Trimmed {cur.rowcount} CONTENT_TYPE rows")
        
        conn.commit()
        cur.close()
        conn.close()
        print("Migration successful")
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == '__main__':
    migrate()
