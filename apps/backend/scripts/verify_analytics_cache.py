
import sys
import os
import time
import logging

# Add backend directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from infrastructure.db_manager import DatabaseManager
from services.analytics_service import count_lemma_occurrences
from services.cache_service import init_cache, get_cache

# Reduce log noise
logging.getLogger("services.cache_service").setLevel(logging.WARNING)
logging.basicConfig(level=logging.WARNING)

def verify_cache():
    print("=== Verifying Analytics Cache (Improved) ===")
    
    # 1. Initialize Cache
    init_cache()
    
    try:
        DatabaseManager.init_pool()
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                # Find a book with actual content chunks
                cursor.execute("""
                    SELECT b.id, b.firebase_uid, b.title 
                    FROM TOMEHUB_BOOKS b
                    WHERE EXISTS (
                        SELECT 1 FROM TOMEHUB_CONTENT c 
                        WHERE c.book_id = b.id 
                    )
                    FETCH NEXT 1 ROWS ONLY
                """)
                row = cursor.fetchone()
                if not row:
                    print("❌ No books with content found.")
                    return
                book_id, uid, title = row
                print(f"📖 Book: '{title}'")
                print(f"🆔 ID: {book_id}")
                
                term = "ve" # Conjunction 'and', very common
                
                # Clear cache first to be sure
                cache = get_cache()
                if cache: cache.clear()

                # 3. First Call (Cold)
                print(f"\n❄️ Call 1 (Cold Stick)...")
                start = time.time()
                count1 = count_lemma_occurrences(uid, book_id, term)
                dur1_ms = (time.time() - start) * 1000
                print(f"   Count: {count1}")
                print(f"   Time:  {dur1_ms:.2f} ms")
                
                # 4. Second Call (Hot)
                print(f"\n🔥 Call 2 (Hot Cache)...")
                start = time.time()
                count2 = count_lemma_occurrences(uid, book_id, term)
                dur2_ms = (time.time() - start) * 1000
                print(f"   Count: {count2}")
                print(f"   Time:  {dur2_ms:.2f} ms")
                
                # Analysis
                print("\n--- Analysis ---")
                if count1 != count2:
                    print(f"❌ MISMATCH! {count1} != {count2}")
                elif dur2_ms < 1.0:
                    print(f"✅ SUCCESS: Cache hit is sub-millisecond ({dur2_ms:.2f} ms).")
                    print(f"🚀 Speedup: {dur1_ms / dur2_ms:.1f}x")
                elif dur2_ms < dur1_ms * 0.1:
                    print(f"✅ SUCCESS: Significant speedup detected.")
                else:
                    print(f"⚠️ UNDETERMINED: Speedup was not drastic ({dur1_ms:.2f} vs {dur2_ms:.2f}). database might be too small/fast.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    verify_cache()
