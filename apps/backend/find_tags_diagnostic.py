
import sys
import os
import json
import ast
from collections import Counter

# Add parent dir to path
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))
from infrastructure.db_manager import DatabaseManager, safe_read_clob

def find_tags():
    DatabaseManager.init_pool()
    all_tags = []
    
    try:
        conn = DatabaseManager.get_connection()
        cursor = conn.cursor()
        
        # 1. Check TOMEHUB_FILE_REPORTS KEY_TOPICS
        print("Checking TOMEHUB_FILE_REPORTS...")
        cursor.execute("SELECT KEY_TOPICS FROM TOMEHUB_FILE_REPORTS")
        rows = cursor.fetchall()
        for r in rows:
            if r[0]:
                try:
                    # It might be a JSON string or a list string
                    data = r[0]
                    if isinstance(data, str):
                        data = json.loads(data)
                    if isinstance(data, list):
                        all_tags.extend(data)
                except:
                    pass
        
        # 2. Check TOMEHUB_CONTENT for embedded "Tags:" lines
        print("Checking TOMEHUB_CONTENT for 'Tags:'...")
        # Search for chunks that likely contain metadata
        cursor.execute("SELECT CONTENT_CHUNK FROM TOMEHUB_CONTENT WHERE CHUNK_INDEX = 0")
        rows = cursor.fetchall()
        for r in rows:
            content = safe_read_clob(r[0])
            if "Tags:" in content:
                # Extract tags: usually "Tags: tag1, tag2, ..."
                for line in content.split('\n'):
                    if line.startswith("Tags:"):
                        tags_str = line.replace("Tags:", "").strip()
                        tags = [t.strip() for t in tags_str.split(',') if t.strip()]
                        all_tags.extend(tags)
        
        counts = Counter([t.lower() for t in all_tags])
        print("\n--- TOP TAGS FOUND ---")
        for tag, count in counts.most_common(50):
            print(f"{tag}: {count}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    find_tags()
