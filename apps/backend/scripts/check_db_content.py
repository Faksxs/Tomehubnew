
import os
import sys
import oracledb
from dotenv import load_dotenv

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.epistemic_service import contains_keyword

def check_db_content():
    # Load env
    load_dotenv(os.path.join(os.getcwd(), 'backend', '.env'))
    
    print("Connecting to DB...")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    dsn = os.getenv("DB_DSN")
    
    conn = oracledb.connect(user=user, password=password, dsn=dsn)
    cursor = conn.cursor()
    
    # Query for the specific chunk seen in screenshot
    query = """
    SELECT content_chunk FROM TOMEHUB_CONTENT 
    WHERE content_chunk LIKE '%Yiğidi kılıç kesmez%'
    FETCH FIRST 1 ROWS ONLY
    """
    
    cursor.execute(query)
    row = cursor.fetchone()
    
    if row:
        content = row[0]
        if hasattr(content, 'read'):
            content = content.read()
            
        print(f"\nRaw Content from DB: {content}")
        print(f"Length: {len(content)}")
        
        keyword = "vicdan"
        match = contains_keyword(content, keyword)
        print(f"\nMatch 'vicdan': {match}")
        
    else:
        print("Note not found in DB!")
        
    conn.close()

if __name__ == "__main__":
    check_db_content()
