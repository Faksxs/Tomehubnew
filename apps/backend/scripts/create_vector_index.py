import os
import sys
import logging
from dotenv import load_dotenv

# Add the parent directory to sys.path so we can import from core
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from core.database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_vector_index():
    logger.info("Connecting to Oracle Database to create Vector Index...")
    
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # Check if index already exists
                cursor.execute("""
                    SELECT count(*) FROM user_indexes 
                    WHERE index_name = 'IDX_TOMEHUB_CONTENT_VEC'
                """)
                if cursor.fetchone()[0] > 0:
                    logger.info("Vector index 'IDX_TOMEHUB_CONTENT_VEC' already exists.")
                    return

                logger.info("Creating In-Memory Neighbor Graph (HNSW) Vector Index...")
                
                # Oracle 23ai Vector Index syntax (HNSW)
                sql = """
                    CREATE VECTOR INDEX IDX_TOMEHUB_CONTENT_VEC 
                    ON TOMEHUB_CONTENT (VEC_EMBEDDING) 
                    ORGANIZATION INMEMORY NEIGHBOR GRAPH 
                    DISTANCE COSINE 
                    WITH TARGET ACCURACY 90
                """
                cursor.execute(sql)
                logger.info("✅ Vector Index created successfully!")
                
    except Exception as e:
        logger.error(f"Failed to create Vector Index: {e}")

if __name__ == "__main__":
    load_dotenv()
    create_vector_index()
