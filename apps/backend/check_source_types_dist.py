
from infrastructure.db_manager import DatabaseManager

def check_source_types():
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    try:
        conn = DatabaseManager.get_read_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT source_type, COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :p_uid GROUP BY source_type", {"p_uid": uid})
        results = cursor.fetchall()
        print(f"Source Type Distribution for {uid}:")
        for st, count in results:
            print(f"  {st}: {count}")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_source_types()
