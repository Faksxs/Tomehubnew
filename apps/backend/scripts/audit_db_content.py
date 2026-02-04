
import os
import sys

# Add parent directory to path to import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from infrastructure.db_manager import DatabaseManager
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def audit_content():
    output_file = "audit_report.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("Starting Database Content Audit...\n")
        
        with DatabaseManager.get_connection() as connection:
            with connection.cursor() as cursor:
                # 1. Count by Source Type
                f.write("\n--- CONTENT BY SOURCE TYPE ---\n")
                cursor.execute("""
                    SELECT source_type, COUNT(*) 
                    FROM TOMEHUB_CONTENT 
                    GROUP BY source_type
                """)
                rows = cursor.fetchall()
                for row in rows:
                    f.write(f"Type: {row[0]} | Count: {row[1]}\n")
                    
                # 2. PDF/EPUB Analysis (Group by Title)
                f.write("\n--- PDF/EPUB BOOKS (Potential Garbage) ---\n")
                cursor.execute("""
                    SELECT title, source_type, COUNT(*) as chunk_count
                    FROM TOMEHUB_CONTENT
                    WHERE source_type IN ('PDF', 'EPUB')
                    GROUP BY title, source_type
                    ORDER BY title
                """)
                pdf_rows = cursor.fetchall()
                
                f.write(f"{'TITLE':<50} | {'TYPE':<10} | {'CHUNKS':<8}\n")
                f.write("-" * 100 + "\n")
                for row in pdf_rows:
                    title = row[0]
                    if title and len(title) > 48: title = title[:45] + "..."
                    type_ = row[1]
                    count = row[2]
                    f.write(f"{title:<50} | {type_:<10} | {count:<8}\n")

                # 3. Check for Anomalies (Null Content)
                f.write("\n--- ANOMALIES ---\n")
                cursor.execute("""
                    SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE content_chunk IS NULL OR LENGTH(content_chunk) < 10
                """)
                empty_count = cursor.fetchone()[0]
                f.write(f"Empty/Tiny Chunks: {empty_count}\n")

                cursor.execute("""
                    SELECT source_type, COUNT(*) 
                    FROM TOMEHUB_CONTENT 
                    GROUP BY source_type
                """)
                rows = cursor.fetchall()
                f.write(f"Unknown Source Types Breakdown:\n")
                for row in rows:
                     f.write(f"Type: '{row[0]}' | Count: {row[1]}\n")

                # 4. DEEP INSPECTION
                f.write("\n--- DEEP INSPECTION (Titles ending in .pdf) ---\n")
                cursor.execute("""
                    SELECT title, source_type 
                    FROM TOMEHUB_CONTENT 
                    WHERE LOWER(title) LIKE '%.pdf' OR LOWER(title) LIKE '%.epub'
                    FETCH FIRST 20 ROWS ONLY
                """)
                filename_rows = cursor.fetchall()
                if not filename_rows:
                    f.write("No titles ending in .pdf/.epub found.\n")
                for row in filename_rows:
                    f.write(f"Title: {row[0]} | Type: {row[1]}\n")

    
    print(f"Audit complete. Results written to {output_file}")


if __name__ == "__main__":
    try:
        audit_content()
    except Exception as e:
        print(f"Error executing audit: {e}")
