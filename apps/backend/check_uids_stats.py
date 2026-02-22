
from infrastructure.db_manager import DatabaseManager

def check_uids():
    bad_uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    good_uid = "vpq1p0UzcCSLAhId18WgZ2wPBE63"
    
    try:
        conn = DatabaseManager.get_read_connection()
        cursor = conn.cursor()
        
        for uid_name, uid_val in [("BAD", bad_uid), ("GOOD", good_uid)]:
            cursor.execute("SELECT COUNT(*) FROM TOMEHUB_BOOKS WHERE firebase_uid = :p_uid", {"p_uid": uid_val})
            books_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid", {"p_uid": uid_val})
            content_count = cursor.fetchone()[0]
            
            print(f"{uid_name} UID ({uid_val}):")
            print(f"  Books: {books_count}")
            print(f"  Content Chunks: {content_count}")
            print("-" * 30)
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_uids()
