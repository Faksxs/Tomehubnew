import os
from infrastructure.db_manager import DatabaseManager

def migrate():
    conn = DatabaseManager.get_connection()
    cursor = conn.cursor()

    try:
        # Clear V2 to be safe if running multiple times
        cursor.execute("TRUNCATE TABLE TOMEHUB_CONTENT_V2")
        print("Truncated TOMEHUB_CONTENT_V2.")
    except Exception as e:
        pass

    sql = """
        INSERT INTO TOMEHUB_CONTENT_V2 (
            FIREBASE_UID,
            ITEM_ID,
            CONTENT_TYPE,
            TITLE,
            CONTENT_CHUNK,
            NORMALIZED_CONTENT,
            TEXT_DEACCENTED,
            LEMMA_TOKENS,
            TOKEN_FREQ,
            CATEGORIES,
            PAGE_NUMBER,
            AI_ELIGIBLE,
            RAG_WEIGHT,
            CHUNK_INDEX,
            VEC_EMBEDDING,
            CREATED_AT,
            UPDATED_AT
        )
        SELECT 
            c.FIREBASE_UID,
            c.BOOK_ID,
            CASE 
                WHEN UPPER(c.SOURCE_TYPE) = 'PERSONAL_NOTE' OR UPPER(c.CHUNK_TYPE) = 'PERSONAL_NOTE' THEN 'PERSONAL_NOTE'
                WHEN UPPER(c.CHUNK_TYPE) = 'INSIGHT' OR UPPER(c.SOURCE_TYPE) = 'INSIGHT' THEN 'INSIGHT'
                WHEN UPPER(c.CHUNK_TYPE) IN ('HIGHLIGHT', 'NOTE') OR UPPER(c.SOURCE_TYPE) IN ('HIGHLIGHT', 'NOTE') THEN 'HIGHLIGHT'
                ELSE 'PDF_CHUNK'
            END,
            c.TITLE,
            c.CONTENT_CHUNK,
            c.NORMALIZED_CONTENT,
            c.TEXT_DEACCENTED,
            c.LEMMA_TOKENS,
            c.TOKEN_FREQ,
            c.CATEGORIES,
            c.PAGE_NUMBER,
            CASE 
                WHEN UPPER(c.SOURCE_TYPE) = 'PERSONAL_NOTE' OR UPPER(c.CHUNK_TYPE) = 'PERSONAL_NOTE' THEN
                    CASE 
                        WHEN UPPER(c.TITLE) LIKE '%PRIVATE%' OR UPPER(c.TITLE) LIKE '%DAILY%' THEN 0
                        WHEN c.TAGS IS NOT NULL AND (DBMS_LOB.INSTR(UPPER(c.TAGS), 'PRIVATE') > 0 OR DBMS_LOB.INSTR(UPPER(c.TAGS), 'DAILY') > 0) THEN 0
                        ELSE 1
                    END
                ELSE 1
            END,
            CASE 
                WHEN UPPER(c.SOURCE_TYPE) = 'PERSONAL_NOTE' OR UPPER(c.CHUNK_TYPE) = 'PERSONAL_NOTE' THEN
                    CASE 
                        WHEN UPPER(c.TITLE) LIKE '%IDEAS%' THEN 0.5
                        WHEN c.TAGS IS NOT NULL AND DBMS_LOB.INSTR(UPPER(c.TAGS), 'IDEAS') > 0 THEN 0.5
                        WHEN UPPER(c.TITLE) LIKE '%PRIVATE%' OR UPPER(c.TITLE) LIKE '%DAILY%' THEN 0.0
                        WHEN c.TAGS IS NOT NULL AND (DBMS_LOB.INSTR(UPPER(c.TAGS), 'PRIVATE') > 0 OR DBMS_LOB.INSTR(UPPER(c.TAGS), 'DAILY') > 0) THEN 0.0
                        ELSE 0.5 
                    END
                ELSE 1.0
            END,
            c.CHUNK_INDEX,
            c.VEC_EMBEDDING,
            c.CREATED_AT,
            c.UPDATED_AT
        FROM TOMEHUB_CONTENT c
        WHERE c.BOOK_ID IS NOT NULL
        -- Only insert if item exists in library items to satisfy Foreign Key CONSTRAINT
        AND EXISTS (SELECT 1 FROM TOMEHUB_LIBRARY_ITEMS li WHERE li.ITEM_ID = c.BOOK_ID AND li.FIREBASE_UID = c.FIREBASE_UID)
    """

    print("Executing batch migration (This might take a few moments for Vector copying)...")
    try:
        cursor.execute(sql)
        conn.commit()
        print(f"Migration completed successfully. Inserted rows: {cursor.rowcount}")
        
        # Verify inserted counts
        cursor.execute("SELECT CONTENT_TYPE, COUNT(*) FROM TOMEHUB_CONTENT_V2 GROUP BY CONTENT_TYPE")
        stats = cursor.fetchall()
        print("\n--- Migration Statistics ---")
        for st in stats:
            print(f"- {st[0]}: {st[1]}")
            
    except Exception as e:
        print(f"Error during migration: {e}")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    migrate()
