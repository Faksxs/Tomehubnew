import os
import sys
import json
import array

# Add backend to path
sys.path.insert(0, os.path.join(os.getcwd(), 'apps', 'backend'))

from services.ingestion_service import get_database_connection

def test_insert():
    print("Testing DB Connection...")
    try:
        conn = get_database_connection()
        print("Connected.")
        
        cursor = conn.cursor()
        
        insert_sql = """
        INSERT INTO TOMEHUB_CONTENT 
        (firebase_uid, source_type, title, content_chunk, chunk_type, page_number, chunk_index, vec_embedding, book_id, normalized_content, text_deaccented, lemma_tokens, passage_type, quotability, classifier_confidence)
        VALUES (:p_uid, :p_type, :p_title, :p_content, :p_chunk_type, :p_page, :p_chunk_idx, :p_vec, :p_book_id, :p_norm_content, :p_deaccent, :p_lemmas, :p_passage_type, :p_quotability, :p_confidence)
        """
        
        # Create a dummy vector (Float32 array, typically 768 dims for Gemini/BERT, or whatever DB expects)
        # Let's assume standard 768 dims which is common, but verify if DB expects something else.
        # Actually, let's try a small one first or array.array('f', [0.1]*768)
        # Oracledb vector type support needs array.array('f') usually.
        
        dummy_vec = array.array('d', [0.1] * 768) # 'd' for double, 'f' for float. Oracle Vectors are often float32
        # WARNING: python-oracledb default double might be issue if DB is float32 vector.
        # Let's try standard list or array.
        
        params = {
            "p_uid": "test_debug_user",
            "p_type": "PDF",
            "p_title": "Debug Insert Title",
            "p_content": "This is a debug content string.",
            "p_chunk_type": "paragraph",
            "p_page": 1,
            "p_chunk_idx": 0,
            "p_vec": str(list(dummy_vec)), # TRYING STRING FIRST b/c often vectors are passed as string "[0.1, ...]" in some drivers or specific array types.
            # actually ingestion_service passes `embedding` which comes from `embedding_service`.
            # Let's check what `batch_get_embeddings` returns. likely a list of floats.
             "p_book_id": "debug_book_id",
             "p_norm_content": "debug content",
             "p_deaccent": "debug content",
             "p_lemmas": "[]",
             "p_passage_type": "SITUATIONAL",
             "p_quotability": "LOW",
             "p_confidence": 0.99
        }
        
        # Real attempt with list of floats (driver should handle or fail)
        params['p_vec'] = array.array('f', [0.1]*768) 

        print("Attempting INSERT...")
        cursor.execute(insert_sql, params)
        print("INSERT successful! Rolling back...")
        conn.rollback()
        
    except Exception as e:
        print(f"INSERT FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    test_insert()
