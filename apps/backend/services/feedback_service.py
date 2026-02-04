
import os
import oracledb
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

from utils.logger import get_logger
logger = get_logger("feedback_service")

def get_database_connection():
    # Helper to get connection (Duplicated for now to avoid circular import issues if imported from search_service)
    # Ideally should be in a common db_utils.py
    user = os.getenv("DB_USER", "ADMIN")
    password = os.getenv("DB_PASSWORD")
    dsn = os.getenv("DB_DSN")
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wallet_location = os.path.join(backend_dir, 'wallet')
    
    return oracledb.connect(
        user=user,
        password=password,
        dsn=dsn,
        config_dir=wallet_location,
        wallet_location=wallet_location,
        wallet_password=password
    )

def submit_feedback(data: dict) -> bool:
    """
    Saves user feedback to TOMEHUB_FEEDBACK table.
    expected data keys: firebase_uid, query, answer, rating, comment
    """
    logger.info("Submitting feedback", extra={"uid": data.get('firebase_uid'), "rating": data.get('rating')})
    if not data.get('search_log_id'):
        logger.warning("Feedback missing search_log_id", extra={"uid": data.get('firebase_uid')})
    
    conn = None
    cursor = None
    
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        
        sql = """
            INSERT INTO TOMEHUB_FEEDBACK 
            (firebase_uid, query_text, generated_answer, rating, feedback_text, context_book_id, search_log_id)
            VALUES (:p_uid, :p_q, :p_ans, :p_rating, :p_comment, :p_bid, :p_log_id)
        """
        
        cursor.execute(sql, {
            "p_uid": data.get('firebase_uid'),
            "p_q": data.get('query'),
            "p_ans": data.get('answer'),
            "p_rating": data.get('rating'), # 1 or 0
            "p_comment": data.get('comment', ''),
            "p_bid": data.get('book_id', None),
            "p_log_id": data.get('search_log_id', None)
        })
        
        conn.commit()
        logger.info("Feedback saved successfully")
        return True
        
    except Exception as e:
        logger.error("Failed to save feedback", extra={"error": str(e)})
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
