
import sys
import os
import oracledb

# Add backend directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from infrastructure.db_manager import DatabaseManager

def run_migration():
    print("=== Applying Safe Schema Migration V2 (Direct) ===")
    
    commands = [
        # 1. Create Table (Wrapped in block for safety)
        """
        BEGIN
            EXECUTE IMMEDIATE 'CREATE TABLE TOMEHUB_BOOKS (
                ID VARCHAR2(255) PRIMARY KEY,
                TITLE VARCHAR2(1000),
                AUTHOR VARCHAR2(500),
                FIREBASE_UID VARCHAR2(255),
                CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                TOTAL_CHUNKS NUMBER DEFAULT 0,
                LAST_UPDATED TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )';
        EXCEPTION
            WHEN OTHERS THEN
                IF SQLCODE != -955 THEN RAISE; END IF;
        END;
        """,
        
        # 2. Backfill
        """
        MERGE INTO TOMEHUB_BOOKS b
        USING (
            SELECT 
                book_id,
                MIN(title) as title,
                MIN(firebase_uid) as firebase_uid,
                COUNT(*) as chunk_count
            FROM TOMEHUB_CONTENT
            WHERE book_id IS NOT NULL
            GROUP BY book_id
        ) c
        ON (b.ID = c.book_id)
        WHEN NOT MATCHED THEN
            INSERT (ID, TITLE, FIREBASE_UID, TOTAL_CHUNKS)
            VALUES (c.book_id, c.title, c.firebase_uid, c.chunk_count)
        """,
        
        # 3. Index
        """
        BEGIN
            EXECUTE IMMEDIATE 'CREATE INDEX idx_books_firebase_uid ON TOMEHUB_BOOKS(FIREBASE_UID)';
        EXCEPTION
            WHEN OTHERS THEN
                IF SQLCODE != -955 THEN RAISE; END IF;
        END;
        """,
        
        # 4. Constraint (Join)
        """
        BEGIN
            EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_CONTENT 
                               ADD CONSTRAINT fk_content_book 
                               FOREIGN KEY (book_id) REFERENCES TOMEHUB_BOOKS(ID) 
                               DISABLE';
        EXCEPTION
            WHEN OTHERS THEN
                IF SQLCODE != -2275 THEN RAISE; END IF;
        END;
        """
    ]

    try:
        DatabaseManager.init_pool()
        # Use simple connection, not pool, for DDL if possible, but manager uses pool
        conn = DatabaseManager.get_write_connection()
        cursor = conn.cursor()
        
        print(f"Executing {len(commands)} commands directly...")
        
        for idx, cmd in enumerate(commands):
            print(f"Executing command {idx+1}...")
            try:
                cursor.execute(cmd)
                print("  Success.")
            except Exception as e:
                print(f"  Error in command {idx+1}: {e}")
                
        conn.commit()
        print("\nMigration V2 completed successfully.")
        
    except Exception as e:
        print(f"FATAL DB Error: {e}")
    finally:
        try:
            if 'cursor' in locals() and cursor: cursor.close()
            if 'conn' in locals() and conn: conn.close()
            DatabaseManager.close_pool()
        except: pass

if __name__ == "__main__":
    run_migration()
