
import os
import time
import oracledb
from datetime import datetime
from dotenv import load_dotenv

import sys
sys.path.append('backend')

# Import Graph Service for extraction logic
from services.graph_service import extract_concepts_and_relations, save_to_graph, get_database_connection

# Load environment
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', '.env')
load_dotenv(dotenv_path=env_path)

def populate_graph_batch(limit=50):
    """
    Fetches content chunks that haven't been processed for the graph yet,
    extracts concepts, and saves them.
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting Graph Population Batch (Limit: {limit})...")
    
    conn = get_database_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Find unprocessed chunks
        # We can identify them by checking if they exist in TOMEHUB_CONCEPT_CHUNKS
        # or just pick random ones for this demo.
        # Ideally, we should have a 'graph_processed' flag in TOMEHUB_CONTENT.
        # For now, let's just pick top N that are NOT in concept_chunks.
        
        sql = """
            SELECT c.id, c.content_chunk, c.title
            FROM TOMEHUB_CONTENT c
            WHERE NOT EXISTS (
                SELECT 1 FROM TOMEHUB_CONCEPT_CHUNKS cc WHERE cc.content_id = c.id
            )
            AND c.content_chunk IS NOT NULL
            AND LENGTH(c.content_chunk) > 100
            FETCH FIRST :lim ROWS ONLY
        """
        
        cursor.execute(sql, {"lim": limit})
        rows = cursor.fetchall()
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(rows)} unprocessed chunks.")
        
        batch_data = []
        for row in rows:
            cid, text_lob, title = row
            # Handle LOB
            text = text_lob.read() if hasattr(text_lob, 'read') else text_lob
            if text:
                # Truncate text if too long to avoid huge payload to Gemini
                batch_data.append((cid, text[:20000], title))
        
        cursor.close()
        conn.close()
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Connection closed. Processing {len(batch_data)} items...")
        
        processed_count = 0
        
        for cid, text, title in batch_data:
            try:
                print(f"Processing [{cid}] {title[:30]}...")
            
                # Extract
                concepts, relations = extract_concepts_and_relations(text)
                
                if concepts:
                    print(f"  -> Found {len(concepts)} concepts, {len(relations)} relations.")
                    # Save (opens new connection)
                    save_to_graph(cid, concepts, relations)
                    processed_count += 1
                    time.sleep(1) 
                else:
                    print("  -> No concepts found.")
            except Exception as e_inner:
                print(f"  [ERROR] Item {cid} failed: {e_inner}")
                
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Batch complete. Processed {processed_count}/{len(batch_data)}.")
        return
        
    except Exception as e:
        print(f"[ERROR] Population failed: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    # Run a small batch to test
    populate_graph_batch(limit=10)
