import os
import sys
import re
import oracledb
from datetime import datetime
from dotenv import load_dotenv

# Load .env first
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(env_path)

# Add backend to path to use config/infrastructure
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from infrastructure.db_manager import DatabaseManager
from config import settings

# --- REGEX LOGIC (Duplicated from smart_search_service for isolation) ---
def parse_and_clean_content(content):
    """
    Parses the content_chunk to extract metadata and clean the main text.
    Returns (clean_text, summary, tags, personal_comment)
    """
    if not content:
        return "", "", "", ""

    summary = ""
    tags = ""
    personal_comment = ""
    
    # 1. Extract Personal Comment (Arsiv Notu)
    comment_pattern = re.compile(r'(?:Note:\s*)?Arsiv Notu\s*[:\-\s]*(.*)', re.IGNORECASE | re.DOTALL)
    comment_match = comment_pattern.search(content)
    if comment_match:
        personal_comment = comment_match.group(1).strip()
        content = content[:comment_match.start()].strip()

    # 2. Extract Tags
    tags_match = re.search(r'^Tags:\s*(.+)$', content, re.MULTILINE | re.IGNORECASE)
    if tags_match:
        tags = tags_match.group(1).strip()
        content = re.sub(r'^Tags:\s*.+$', '', content, flags=re.MULTILINE | re.IGNORECASE)

    # 3. Extract Notes/Summary
    summary_match = re.search(r'^Notes:\s*(.+)$', content, re.MULTILINE | re.IGNORECASE)
    if summary_match:
        summary = summary_match.group(1).strip()
        content = re.sub(r'^Notes:\s*.+$', '', content, flags=re.MULTILINE | re.IGNORECASE)

    # 4. Strip final prefixes (Title, Author, Highlight from...)
    patterns = [
        r'^Highlight from .+?:\s*',
        r'^Title:\s*.+?(\n|$)',
        r'^Author:\s*.+?(\n|$)',
        r'^Note:\s*',
    ]
    
    for pattern in patterns:
        content = re.sub(pattern, '', content, flags=re.MULTILINE | re.IGNORECASE)

    clean_text = content.strip()
    return clean_text, summary, tags, personal_comment

def run_migration():
    print("Starting Data Normalization Migration...")
    
    # Manually init pool or just connect directly since this is a script
    # Direct connection is simpler for a script to avoid lifespan complexity
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wallet_location = os.path.join(backend_dir, 'wallet')
    
    conn = oracledb.connect(
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        dsn=settings.DB_DSN,
        config_dir=wallet_location,
        wallet_location=wallet_location,
        wallet_password=settings.DB_PASSWORD
    )
    cursor = conn.cursor()
    
    try:
        # 1. Get total count
        cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE NORMALIZED_STATUS IS NULL")
        total_rows = cursor.fetchone()[0]
        print(f"Total rows to migrate: {total_rows}")
        
        if total_rows == 0:
            print("Migration already complete.")
            return

        # 2. Iterate and Update
        BATCH_SIZE = 50
        processed = 0
        
        while True:
            cursor.execute("""
                SELECT ROWID, content_chunk 
                FROM TOMEHUB_CONTENT 
                WHERE NORMALIZED_STATUS IS NULL 
                FETCH FIRST :limit ROWS ONLY
            """, {"limit": BATCH_SIZE})
            
            rows = cursor.fetchall()
            if not rows:
                break
                
            for rid, content_clob in rows:
                # Read CLOB
                content_text = content_clob.read() if content_clob else ""
                
                # Parse
                clean_text, summary, tags, p_note = parse_and_clean_content(content_text)
                
                # Oracle treats empty string as NULL. If content became empty after cleaning,
                # use a space to avoid ORA-01407 (NOT NULL constraint) or keep original if critical.
                # Here we use a space to indicate "content is effectively just metadata".
                if not clean_text:
                    clean_text = " "
                
                # Update
                cursor.execute("""
                    UPDATE TOMEHUB_CONTENT 
                    SET content_chunk = :clean,
                        summary = :summ,
                        tags = :tags,
                        personal_note = :note,
                        normalized_status = 'DONE'
                    WHERE ROWID = :rid
                """, {
                    "clean": clean_text,
                    "summ": summary,
                    "tags": tags,
                    "note": p_note,
                    "rid": rid
                })
                
                processed += 1
                if processed % 10 == 0:
                    print(f"Processed {processed}/{total_rows}...")
            
            conn.commit() # Commit every batch
            print(f"Batch committed. Total processed so far: {processed}")

    except Exception as e:
        print(f"Migration Failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
        print("Migration Script Finished.")

if __name__ == "__main__":
    run_migration()
