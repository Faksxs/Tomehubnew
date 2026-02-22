import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infrastructure.db_manager import DatabaseManager

def check_api(uid):
    DatabaseManager.init_pool()
    try:
        from services.library_service import get_user_books
        books = get_user_books(uid)
        found = False
        for b in books:
            title = b.get("title", "")
            if "Klasik" in title or "Sosyoloji" in title:
                print(f"FOUND IN API -> ID: {b.get('id')} | Title: {title} | Type: {b.get('source_type')}")
                found = True
        if not found:
            print("Not found in Oracle library API either.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    check_api("vpq1p0UzcCSLAh1d18WgZZeTebh1")
