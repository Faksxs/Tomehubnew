import os
from infrastructure.db_manager import DatabaseManager

def apply_schema():
    conn = DatabaseManager.get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DROP TABLE TOMEHUB_CONTENT_V2 CASCADE CONSTRAINTS")
        print("Dropped existing TOMEHUB_CONTENT_V2.")
    except Exception:
        pass

    statements = [
        """
        CREATE TABLE TOMEHUB_CONTENT_V2 (
            ID NUMBER GENERATED ALWAYS AS IDENTITY,
            FIREBASE_UID VARCHAR2(255) NOT NULL,
            ITEM_ID VARCHAR2(255) NOT NULL, 
            CONTENT_TYPE VARCHAR2(50) NOT NULL, 
            TITLE VARCHAR2(1000), 
            CONTENT_CHUNK CLOB NOT NULL,
            NORMALIZED_CONTENT CLOB,
            PAGE_NUMBER NUMBER,
            PARAGRAPH_NUMBER NUMBER,
            CHAPTER_NAME VARCHAR2(500),
            COMMENT_TEXT CLOB,
            TAGS_JSON CLOB CHECK (TAGS_JSON IS JSON),
            NOTE_DATE DATE,
            AI_ELIGIBLE NUMBER(1) DEFAULT 1 CHECK (AI_ELIGIBLE IN (0, 1)),
            RAG_WEIGHT NUMBER DEFAULT 1.0, 
            CHUNK_INDEX NUMBER,
            VEC_EMBEDDING VECTOR(768, FLOAT32),
            CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
            UPDATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PARTITION_MONTH DATE GENERATED ALWAYS AS (TRUNC(CREATED_AT, 'MM')) VIRTUAL,
            CONSTRAINT pk_tomehub_content_v2 PRIMARY KEY (ID)
        )
        PARTITION BY RANGE (PARTITION_MONTH) 
        INTERVAL(NUMTOYMINTERVAL(1, 'MONTH'))
        (
            PARTITION p_initial VALUES LESS THAN (TO_DATE('2024-01-01', 'YYYY-MM-DD'))
        )
        """,
        """
        ALTER TABLE TOMEHUB_CONTENT_V2 
        ADD CONSTRAINT fk_content_v2_library_item 
        FOREIGN KEY (FIREBASE_UID, ITEM_ID) 
        REFERENCES TOMEHUB_LIBRARY_ITEMS (FIREBASE_UID, ITEM_ID) 
        DEFERRABLE INITIALLY DEFERRED
        """,
        "CREATE INDEX idx_cnt_uid_v2 ON TOMEHUB_CONTENT_V2(FIREBASE_UID, ITEM_ID) LOCAL",
        "CREATE INDEX idx_cnt_ai_eligible_v2 ON TOMEHUB_CONTENT_V2(FIREBASE_UID, AI_ELIGIBLE) LOCAL",
        "CREATE INDEX idx_cnt_type_v2 ON TOMEHUB_CONTENT_V2(CONTENT_TYPE, FIREBASE_UID) LOCAL",
        """
        CREATE VECTOR INDEX idx_cnt_vec_v2 ON TOMEHUB_CONTENT_V2(VEC_EMBEDDING) 
        ORGANIZATION NEIGHBOR PARTITIONS
        DISTANCE COSINE
        WITH TARGET ACCURACY 95
        """
    ]

    for stmt in statements:
        try:
            print(f"Executing: {stmt[:50]}...")
            cursor.execute(stmt)
            print("Success.")
        except Exception as e:
            if "ORA-00955" in str(e): 
                print("Already exists.")
            else:
                print(f"Error: {e}")
                
    conn.commit()
    cursor.close()
    conn.close()
    print("Schema apply finished.")

if __name__ == "__main__":
    apply_schema()
