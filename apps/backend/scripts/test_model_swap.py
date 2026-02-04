
import os
import sys
import asyncio

# Setup path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.embedding_service import get_embedding

def test_new_model():
    print("🚀 Testing 'gemini-embedding-001'...")
    try:
        text = "Test sentence for embedding model validation."
        vec = get_embedding(text)
        
        if vec:
            print(f"✅ Success! Generated vector of length: {len(vec)}")
            if len(vec) == 768:
                print("✅ Dimension check PASSED (768)")
            else:
                print(f"❌ Dimension mismatch! Expected 768, got {len(vec)}")
        else:
            print("❌ Failed to generate embedding (Result is None).")
            
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    test_new_model()
