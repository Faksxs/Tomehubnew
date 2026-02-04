import io
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.db_manager import DatabaseManager, safe_read_clob
import google.generativeai as genai
import array

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

BATCH_SIZE = 50

def batch_get_embeddings_fallback(texts):
    if not texts:
        return []
    if not api_key:
        raise ValueError("GEMINI_API_KEY not configured")
    result = genai.embed_content(
        model="models/gemini-embedding-001",
        content=texts,
        task_type="retrieval_document",
        output_dimensionality=768,
        request_options={'timeout': 30}
    )
    if hasattr(result, 'embeddings'):
        embeddings = result.embeddings
    elif isinstance(result, dict):
        if 'embeddings' in result:
            embeddings = result.get('embeddings', [])
        elif 'embedding' in result:
            embeddings = result.get('embedding', [])
        else:
            embeddings = []
    else:
        embeddings = []
    normalized = []
    for emb in embeddings:
        if not emb:
            normalized.append(None)
            continue
        # emb might be list[float]
        try:
            normalized.append(array.array("f", emb))
        except Exception:
            normalized.append(None)
    return normalized

def backfill_description_embeddings():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, name, description
                    FROM TOMEHUB_CONCEPTS
                    WHERE DESCRIPTION_EMBEDDING IS NULL
                """)
                rows = cursor.fetchall()

        if not rows:
            print("NO_ROWS_TO_BACKFILL")
            return

        print(f"TO_BACKFILL={len(rows)}")

        # Process in batches
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i+BATCH_SIZE]
            texts = []
            ids = []
            for cid, name, desc in batch:
                desc_text = safe_read_clob(desc) if desc else ""
                text = desc_text.strip() if desc_text and len(desc_text.strip()) > 10 else (name or "").strip()
                if not text:
                    continue
                ids.append(cid)
                texts.append(text)

            if not texts:
                continue

            embeddings = batch_get_embeddings_fallback(texts)
            with DatabaseManager.get_write_connection() as conn:
                with conn.cursor() as cursor:
                    for cid, emb in zip(ids, embeddings):
                        if emb is None:
                            continue
                        cursor.execute("""
                            UPDATE TOMEHUB_CONCEPTS
                            SET DESCRIPTION_EMBEDDING = :p_vec
                            WHERE ID = :p_id
                        """, {"p_vec": emb, "p_id": cid})
                conn.commit()

            print(f"BATCH_DONE {min(i+BATCH_SIZE, len(rows))}/{len(rows)}")

        print("BACKFILL_COMPLETE")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    backfill_description_embeddings()
