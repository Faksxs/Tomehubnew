
import os
import sys
import asyncio

# Setup path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Correct import based on file analysis
from services.ingestion_service import ingest_book
from infrastructure.db_manager import DatabaseManager

def debugingest():
    # File found in uploads dir
    filename = "aae81e2c-5062-40b4-8911-111bd4e962de_Theodor_W._Adorno_-_Ahlak_Felsefesinin_Sorunlar.pdf"
    file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", filename)
    
    print(f"🚀 Starting Manual Ingest Debug for: {filename}")
    
    if not os.path.exists(file_path):
        print(f"❌ File not found at: {file_path}")
        return

    # Use a dummy UID for testing since we can't easily map the exact one without more info
    # The previous script successfully checked DB with 'test_user_001' or similar context?
    # Actually, let's use a known UID if possible. 
    # I'll use "test_user_001" as a safe fallback or just "debug_user"
    target_uid = "test_user_001"
    
    try:
        DatabaseManager.init_pool()
        
        print("⚡ calling ingest_book...")
        
        title = "Ahlak Felsefesinin Sorunları"
        author = "Theodor W. Adorno"
        
        # ingest_book is synchronous?
        # Definition: ingest_book(file_path, title, author, firebase_uid, ...)
        
        result = ingest_book(
            file_path=file_path,
            title=title,
            author=author,
            firebase_uid=target_uid
        )
        
        print(f"✅ Ingestion Result: {result}")

    except Exception as e:
        print(f"\n❌ INGESTION FAILED WITH ERROR:")
        print("-" * 40)
        import traceback
        traceback.print_exc()
        print("-" * 40)

if __name__ == "__main__":
    debugingest()
