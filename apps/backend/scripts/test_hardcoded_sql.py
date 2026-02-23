
import sys
import os
sys.path.append(os.getcwd())
from infrastructure.db_manager import DatabaseManager

def test_hardcoded_merge():
    print("--- Hardcoded MERGE Test ---")
    try:
        with DatabaseManager.get_write_connection() as conn:
            cursor = conn.cursor()
            
            # Simple test data
            p_bid = "TEST_BOOK_ID"
            p_uid = "TEST_UID"
            p_summary = "Test Summary"
            p_topics = "[]"
            p_entities = "[]"
            
            merge_sql = """
            MERGE INTO TOMEHUB_FILE_REPORTS target
            USING (SELECT :p_bid as b_id, :p_uid as u_id FROM DUAL) src
            ON (target."BOOK_ID" = src.b_id AND target."FIREBASE_UID" = src.u_id)
            WHEN MATCHED THEN
                UPDATE SET 
                    "SUMMARY_TEXT" = :p_summary,
                    "KEY_TOPICS" = :p_topics,
                    "ENTITIES" = :p_entities,
                    "UPDATED_AT" = CURRENT_TIMESTAMP
            WHEN NOT MATCHED THEN
                INSERT ("BOOK_ID", "FIREBASE_UID", "SUMMARY_TEXT", "KEY_TOPICS", "ENTITIES", "CREATED_AT", "UPDATED_AT")
                VALUES (src.b_id, src.u_id, :p_summary, :p_topics, :p_entities, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
            
            cursor.execute(merge_sql, {
                "p_bid": p_bid,
                "p_uid": p_uid,
                "p_summary": p_summary,
                "p_topics": p_topics,
                "p_entities": p_entities
            })
            conn.commit()
            print("✓ Hardcoded MERGE successful!")
            
    except Exception as e:
        print(f"✗ Hardcoded MERGE failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_hardcoded_merge()
