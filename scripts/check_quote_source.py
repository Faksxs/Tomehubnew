import sys
import os

# Add apps/backend to path
sys.path.insert(0, os.path.join(os.getcwd(), 'apps', 'backend'))

from services.ingestion_service import get_database_connection

def check_quote():
    # The quote from the screenshot
    quote_snippet = "Ona göre esas olan zaman dediğimiz şeyi insan ruhunun benimsemesi"
    
    try:
        conn = get_database_connection()
        cursor = conn.cursor()
        
        # Search for this text in content columns
        # We check both NORMALIZED_CONTENT (used for search) and CONTENT_CHUNK (raw text)
        query = """
        SELECT source_type, title, is_note, content_chunk
        FROM TOMEHUB_CONTENT 
        WHERE 
            firebase_uid = :p_uid 
            AND (DBMS_LOB.INSTR(content_chunk, :p_quote) > 0 OR DBMS_LOB.INSTR(normalized_content, :p_quote) > 0)
        """
        
        # We need to use a slightly simpler query for LIKE if LOB functions differ, 
        # but DBMS_LOB.INSTR is standard for CLOBs in Oracle.
        # Alternatively, using LIKE for simplicity if the text isn't massive CLOBs in this context logic
        query_simple = """
        SELECT source_type, title, is_note
        FROM TOMEHUB_CONTENT 
        WHERE firebase_uid = :p_uid AND content_chunk LIKE '%' || :p_quote || '%'
        """

        cursor.execute(query_simple, {"p_uid": "vpq1p0UzcCSLAh1d18WgZZWPBE63", "p_quote": quote_snippet})
        rows = cursor.fetchall()
        
        print(f"Searching for: '{quote_snippet}'")
        if not rows:
            print("No exact match found in DB.")
        else:
            print(f"Found {len(rows)} matches:")
            for row in rows:
                source_type = row[0]
                title = row[1]
                is_note = row[2]
                print(f" - Source: {source_type} | Title: {title} | Is Note: {is_note}")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_quote()
