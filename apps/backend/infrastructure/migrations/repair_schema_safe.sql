-- Safe Schema Repair: Create TOMEHUB_BOOKS Mirror
-- 1. Create the table if it doesn't exist
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
        IF SQLCODE != -955 THEN -- ORA-00955: name is already used by an existing object
            RAISE;
        END IF;
END;
/

-- 2. Backfill from TOMEHUB_CONTENT
-- We use MERGE to insert missing books without duplicates
MERGE INTO TOMEHUB_BOOKS b
USING (
    SELECT 
        book_id,
        MIN(title) as title, -- Pick arbitrary title/author for grouping
        MIN(firebase_uid) as firebase_uid, -- Assuming book belongs to one user primarily
        COUNT(*) as chunk_count
    FROM TOMEHUB_CONTENT
    WHERE book_id IS NOT NULL
    GROUP BY book_id
) c
ON (b.ID = c.book_id)
WHEN NOT MATCHED THEN
    INSERT (ID, TITLE, FIREBASE_UID, TOTAL_CHUNKS)
    VALUES (c.book_id, c.title, c.firebase_uid, c.chunk_count);

-- 3. Add Index for Performance
BEGIN
    EXECUTE IMMEDIATE 'CREATE INDEX idx_books_firebase_uid ON TOMEHUB_BOOKS(FIREBASE_UID)';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN -- Index already exists
            RAISE;
        END IF;
END;
/

-- 4. Add Constraints (Safe Mode - DISABLE first)
-- We add the constraint but disable it to prevent locking or immediate failures
BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE TOMEHUB_CONTENT 
                       ADD CONSTRAINT fk_content_book 
                       FOREIGN KEY (book_id) REFERENCES TOMEHUB_BOOKS(ID) 
                       DISABLE';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -2275 THEN -- ORA-02275: such a referential constraint already exists
            RAISE;
        END IF;
END;
/

-- 5. Enable Constraints NOVALIDATE (Fast enable, checks new data, ignores old)
-- Uncomment this line to enforce integrity on NEW inserts only
-- ALTER TABLE TOMEHUB_CONTENT ENABLE NOVALIDATE CONSTRAINT fk_content_book;
