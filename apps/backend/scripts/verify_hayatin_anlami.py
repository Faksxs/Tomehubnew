
import os

import sys
import codecs

# Force localized output to handle Turkish characters
sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.db_manager import DatabaseManager


def verify_hayatin_anlami():
    title_keyword = "Hayatın Anlamı"
    output_path = "verify_output.txt"
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"🔍 Verifying status for '{title_keyword}'...\n\n")
        
        try:
            DatabaseManager.init_pool()
            
            with DatabaseManager.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 1. Check chunks count
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM TOMEHUB_CONTENT 
                        WHERE LOWER(title) LIKE LOWER(:p_title)
                        AND source_type IN ('PDF', 'EPUB', 'PDF_CHUNK')
                    """, {"p_title": f"%{title_keyword}%"})
                    row = cursor.fetchone()
                    count = row[0]
                    # date = row[1]
                    
                    f.write(f"📊 PDF Chunk Count: {count}\n")
                    if count > 0:
                        f.write(f"✅ DB: Records Found ({count} chunks)\n")
                    else:
                        f.write("❌ DB: No specific records found for 'Hayatın Anlamı'.\n")
                        
                    # 2. List ALL recent PDFs to check for title mismatch
                    f.write("\n🔎 Checking ANY recent PDF uploads (Last 10):\n")
                    cursor.execute("""
                        SELECT DISTINCT title, source_type 
                        FROM TOMEHUB_CONTENT 
                        WHERE source_type IN ('PDF', 'EPUB', 'PDF_CHUNK')
                        FETCH FIRST 10 ROWS ONLY
                    """)
                    rows = cursor.fetchall()
                    if rows:
                        for r in rows:
                            f.write(f"   - [{r[1]}] {r[0]}\n")
                    else:
                        f.write("   (No PDF content found in entire DB)\n")

        except Exception as e:
            f.write(f"Error: {e}\n")

        # 3. Check file system for cleanup
        uploads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
        f.write(f"\n📂 Checking Uploads Directory ({uploads_dir}):\n")
        found = False
        if os.path.exists(uploads_dir):
            for filename in os.listdir(uploads_dir):
                if "Hayatın" in filename or "Anlamı" in filename:  # Fuzzy match filename
                    f.write(f"   ⚠️  File FOUND (Not Deleted): {filename}\n")
                    found = True
        
        if not found:
            f.write("   ✅ File CLEAN (No matching PDF found in uploads)\n")

if __name__ == "__main__":
    verify_hayatin_anlami()
