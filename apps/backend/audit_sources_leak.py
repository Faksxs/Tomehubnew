
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.db_manager import DatabaseManager

def audit_sources():
    DatabaseManager.init_pool()
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # 1. Check all distinct source types
            print("\n--- DISTINCT SOURCE TYPES ---")
            cursor.execute("SELECT DISTINCT source_type FROM TOMEHUB_CONTENT")
            for row in cursor.fetchall():
                print(row[0])
                
            # 2. Check "NOTES" sample to see if they look like articles/websites
            print("\n--- SAMPLE 'NOTES' (Highlights) ---")
            cursor.execute("SELECT title, content_chunk FROM TOMEHUB_CONTENT WHERE source_type = 'NOTES' FETCH FIRST 20 ROWS ONLY")
            for row in cursor.fetchall():
                try:
                    content = row[1].read() if hasattr(row[1], 'read') else str(row[1])
                except:
                    content = str(row[1])
                print(f"Title: {row[0]}")
                print(f"Content: {content[:50]}...")
                print("-" * 20)
                
            # 3. Check "Dogum gunu - Self" source type
            print("\n--- 'Dogum gunu - Self' ANALYSIS ---")
            cursor.execute("SELECT id, source_type, title FROM TOMEHUB_CONTENT WHERE title LIKE '%Dogum gunu%'")
            for row in cursor.fetchall():
                print(f"Title: {row[2]}")
                print(f"Source Type: {row[1]}")

            # 4. Check 'ARTICLE' and 'WEBSITE' existence
            print("\n--- ARTICLE / WEBSITE COUNT ---")
            cursor.execute("SELECT source_type, COUNT(*) FROM TOMEHUB_CONTENT WHERE source_type IN ('ARTICLE', 'WEBSITE') GROUP BY source_type")
            for row in cursor.fetchall():
                print(f"{row[0]}: {row[1]}")

if __name__ == "__main__":
    audit_sources()
