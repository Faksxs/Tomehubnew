
import os
import sys
import io

# Handle Turkish encoding in windows terminal
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

def check_reingestion():
    DatabaseManager.init_pool()
    print("--- Checking Re-ingestion for 'Hayat' ---")
    
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Get Title and Source Type
                cursor.execute("""
                    SELECT DISTINCT title, source_type, firebase_uid 
                    FROM TOMEHUB_CONTENT 
                    WHERE title LIKE '%Hayat%' OR title LIKE '%Terry%'
                """)
                rows = cursor.fetchall()
                print(f"Found {len(rows)} matching book records:")
                for r in rows:
                    print(f"Title: '{r[0]}' | Type: {r[1]} | UID: {r[2]}")
                
                if not rows:
                    print("❌ No book found! Ingestion might have failed or is still running.")
                    return

                target_title = rows[0][0] # Pick the first one
                print(f"Targeting: {target_title}")
                
                # 2. Check Content Quality (Random sampling)
                print(f"\n--- Sampling Content from '{target_title}' ---")
                cursor.execute("""
                    SELECT content_chunk 
                    FROM TOMEHUB_CONTENT 
                    WHERE title = :p_title AND ROWNUM <= 3
                """, {"p_title": target_title})
                
                chunks = cursor.fetchall()
                for i, chunk in enumerate(chunks):
                    text = chunk[0].read() if hasattr(chunk[0], 'read') else str(chunk[0])
                    print(f"\n[Chunk {i+1} Sample]:")
                    print(text[:300]) 
                    
                    tilde_count = text.count('~')
                    print(f"Stats: Tilde count: {tilde_count}")
                    
                    if "günümüz" in text.lower():
                        print("✅ Found 'günümüz'")
                    elif "gOnOmuz" in text:
                        print("❌ Found 'gOnOmuz' (ERROR)")
                    elif "gonomuz" in text.lower():
                         print("❌ Found 'gonomuz' (ERROR)")

                if not chunks:
                    print("No chunks found in TOMEHUB_CONTENT for this title.")
                        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    check_reingestion()
