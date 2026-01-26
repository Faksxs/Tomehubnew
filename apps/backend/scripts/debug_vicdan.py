"""
Debug: Find the user's specific definitional vicdan note
"""
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from services.smart_search_service import perform_smart_search

def find_definitional_note():
    print("="*70)
    print("Finding user's definitional note")
    print("="*70)
    
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    
    # Search for the exact text the user provided
    search_terms = [
        "İyiyi kötüden ayırma",  # From note #1
        "vicdan için iki teori",  # From note #4
        "vicdandır halbuki",      # Key phrase from note #1
    ]
    
    for term in search_terms:
        print(f"\n[SEARCH] '{term}'")
        results = perform_smart_search(term, uid)
        
        if results:
            print(f"  Found {len(results)} results")
            for i, chunk in enumerate(results[:3], 1):
                content = chunk.get('content_chunk', '')
                if hasattr(content, 'read'):
                    content = content.read()
                content = str(content)[:150]
                title = chunk.get('title', 'Unknown')
                print(f"  {i}. {title}: {content}...")
        else:
            print(f"  NO RESULTS")

if __name__ == "__main__":
    find_definitional_note()
