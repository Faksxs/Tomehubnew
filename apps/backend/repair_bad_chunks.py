
import os
import sys
import re

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

def clean_text_artifacts(text: str) -> str:
    """
    Clean common OCR and encoding artifacts from extracted text,
    specifically targeting Turkish character corruptions.
    """
    if not text:
        return text
        
    # 1. Fix numeric '1' acting as 'ı' or 'l' inside words
    text = re.sub(r'(?<=[a-zA-ZçğıöşüÇĞİÖŞÜ])1(?=[a-zA-ZçğıöşüÇĞİÖŞÜ])', 'ı', text)
    text = re.sub(r'(?<=[a-zçğıöşü])1\b', 'ı', text)

    # 2. Fix Tilde '~' usages
    replacements = {
        r'\b~ok\b': 'çok',
        r'~ok\b': 'çok',
        r'\bi~in\b': 'için',
        r'\bi~inde': 'içinde',
        r'\bge~me': 'geçme',
        r'~ünkü': 'çünkü',
        r'~ıkış': 'çıkış',
        r'~alış': 'çalış',
        r'ka~Tn': 'kaçın',
        r'sonu~': 'sonuç',
        r'ama~': 'amaç',
        r'b~r': 'bir',
        r'olu~tur': 'oluştur',
        r'geli~': 'geliş',
        r'deği~': 'değiş',
        r'konu~': 'konuş',
        r'ya~a': 'yaşa',
        r'dönu~': 'dönüş',
        r'~': 'ş', # Aggressive fallback for remaining tildes if sandwiched?
    }
    
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # 3. Aggressive tilde fallback:
    # If ~ is surrounded by letters, it's likely a missing char.
    # "olu~tur" -> ş. "ba~la" -> ş.
    # Let's try to map typical contexts.
    
    # 4. Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def repair_content():
    print("Initializing DB Pool...")
    DatabaseManager.init_pool()
    
    try:
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                print("Fetching corrupted chunks...")
                cursor.execute("""
                    SELECT id, content_chunk 
                    FROM TOMEHUB_CONTENT 
                    WHERE title LIKE 'Hayatin Anlami - Terry Eagleton%' 
                """)
                
                rows = cursor.fetchall()
                print(f"Found {len(rows)} rows to inspect.")
                
                updated_count = 0
                for row in rows:
                    chunk_id = row[0]
                    original_text = row[1]
                    
                    # Handle LOB objects
                    if hasattr(original_text, 'read'):
                        original_text = original_text.read()
                    
                    if not original_text:
                        continue
                        
                    cleaned_text = clean_text_artifacts(original_text)
                    
                    if cleaned_text and cleaned_text != original_text:
                        cursor.execute("""
                            UPDATE TOMEHUB_CONTENT 
                            SET content_chunk = :p_text 
                            WHERE id = :p_id
                        """, {"p_text": cleaned_text, "p_id": chunk_id})
                        updated_count += 1
                        if updated_count % 10 == 0:
                            print(f"Updated {updated_count} chunks...")
                            conn.commit()
                
                conn.commit()
                print(f"✅ Repaired {updated_count} chunks out of {len(rows)}.")
                    
    except Exception as e:
        print(f"Repair failed: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    repair_content()
