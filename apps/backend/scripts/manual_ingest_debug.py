
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
    # filename = "aae81e2c-5062-40b4-8911-111bd4e962de_Theodor_W._Adorno_-_Ahlak_Felsefesinin_Sorunlar.pdf"
    # file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", filename)
    
    if len(sys.argv) < 5:
        print("Usage: python manual_ingest_debug.py <path> <title> <author> <uid>")
        sys.exit(1)
        
    target_path = sys.argv[1]
    target_title = sys.argv[2]
    target_author = sys.argv[3]
    target_uid = sys.argv[4]

    print(f"🚀 Starting Manual Ingest Debug for: {target_path}")
    
    if not os.path.exists(target_path):
        print(f"❌ File not found at: {target_path}")
        return

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
