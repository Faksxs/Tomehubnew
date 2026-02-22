import os
import sys

# Add apps/backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager
from app import upsert_ingestion_status

def fix():
    DatabaseManager.init_pool()
    try:
        book_id = '1771631518661'
        firebase_uid = 'vpq1p0UzcCSLAh1d18WgZZeTebh1'
        
        # Get counts
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT count(*), sum(case when vec_embedding is not null then 1 else 0 end)
                    FROM TOMEHUB_CONTENT 
                    WHERE book_id = :p_bid
                ''', {"p_bid": book_id})
                row = cursor.fetchone()
                chunk_count = row[0] if row else 0
                emb_count = row[1] if row and row[1] is not None else 0
                
        print(f"Chunks: {chunk_count}, Embeddings: {emb_count}")
        
        # Upsert
        upsert_ingestion_status(
            book_id=book_id,
            firebase_uid=firebase_uid,
            status="COMPLETED",
            chunk_count=chunk_count,
            embedding_count=emb_count
        )
        print("Updated status to COMPLETED.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == '__main__':
    fix()
