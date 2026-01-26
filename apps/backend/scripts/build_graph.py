
import os
import sys
import time
import oracledb
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path to import services
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.append(backend_dir)

try:
    from services.graph_service import extract_concepts_and_relations, save_to_graph, get_database_connection
except ImportError as e:
    print(f"Error importing services: {e}")
    print(f"sys.path: {sys.path}")
    sys.exit(1)

# Load environment variables explicitly to be safe
load_dotenv(os.path.join(backend_dir, '.env'))

def build_graph_for_all_content():
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
    except Exception as e:
        print(f"Failed to connect to DB: {e}")
        return
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting GraphRAG Enrichment...")
    
    try:
        # Get content that hasn't been processed
        # We check TOMEHUB_CONCEPT_CHUNKS to see if content_id is already linked to ANY concept
        # Fetching a batch of 20 to avoid long running processes during tests
        cursor.execute("""
            SELECT c.id, c.content_chunk, c.title 
            FROM TOMEHUB_CONTENT c
            WHERE NOT EXISTS (
                SELECT 1 FROM TOMEHUB_CONCEPT_CHUNKS cc WHERE cc.content_id = c.id
            )
            AND c.content_chunk IS NOT NULL
            FETCH FIRST 20 ROWS ONLY
        """)
        
        rows = cursor.fetchall()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Found {len(rows)} items to process in this batch.")
        
        for row in rows:
            content_id = row[0]
            text_clob = row[1]
            title = row[2] if row[2] else "Untitled"
            
            # Handle CLOB
            text = text_clob.read() if hasattr(text_clob, 'read') else str(text_clob)
            
            if not text or len(text) < 50:
                print(f"Skipping ID {content_id} (Text too short)")
                continue
                
            print(f"\nProcessing ID {content_id}: {title[:40]}...")
            
            # 1. Extract
            try:
                concepts, relations = extract_concepts_and_relations(text)
            except Exception as e:
                print(f" -> Extraction failed: {e}")
                continue
            
            if not concepts:
                print(" -> No concepts found (Gemini returned empty).")
                # Optional: Mark as processed to avoid infinite loops? 
                # For now, we skip. Next run will pick it up again unless we flag it.
                continue
                
            print(f" -> Found {len(concepts)} concepts and {len(relations)} relations.")
            
            # 2. Save
            try:
                save_to_graph(content_id, concepts, relations)
                print(" -> Saved to Graph tables.")
            except Exception as e:
                print(f" -> Error saving to graph: {e}")
            
            # Rate limiting for Gemini API (free tier limits)
            time.sleep(2) 
            
    except Exception as e:
        print(f"Error executing batch: {e}")
    finally:
        cursor.close()
        conn.close()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Batch complete.")

if __name__ == "__main__":
    build_graph_for_all_content()
