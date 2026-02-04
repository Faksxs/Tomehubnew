import io
import os
import sys
from dotenv import load_dotenv

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)
load_dotenv(os.path.join(backend_dir, '.env'))

from infrastructure.db_manager import DatabaseManager

def backfill_strength():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # Single-pass update to refresh all strength values
                cursor.execute("""
                    UPDATE TOMEHUB_CONCEPT_CHUNKS cc
                    SET strength = (
                        SELECT 1 - VECTOR_DISTANCE(c.description_embedding, ct.vec_embedding, COSINE)
                        FROM TOMEHUB_CONCEPTS c
                        JOIN TOMEHUB_CONTENT ct ON ct.id = cc.content_id
                        WHERE c.id = cc.concept_id AND ct.id = cc.content_id
                    )
                    WHERE EXISTS (
                        SELECT 1
                        FROM TOMEHUB_CONCEPTS c
                        JOIN TOMEHUB_CONTENT ct ON ct.id = cc.content_id
                        WHERE c.id = cc.concept_id
                          AND c.description_embedding IS NOT NULL
                          AND ct.vec_embedding IS NOT NULL
                    )
                """)
                conn.commit()
                print(f"UPDATED_ROWS={cursor.rowcount}")

        print("BACKFILL_COMPLETE")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    backfill_strength()
