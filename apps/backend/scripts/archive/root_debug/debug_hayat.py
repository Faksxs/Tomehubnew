
from infrastructure.db_manager import DatabaseManager
from services.analytics_service import count_all_notes_occurrences

def debug_hayat():
    uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    term = "hayat"
    
    with open("debug_hayat.log", "w", encoding="utf-8") as log:
        log.write(f"UID: {uid}\n")
        log.write(f"Term: {term}\n")
        
        # 1. Check direct count
        count = count_all_notes_occurrences(uid, term)
        log.write(f"Current implementation count: {count}\n")
        
        # 2. Inspect DB for all source types
        try:
            with DatabaseManager.get_read_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT source_type, COUNT(*) 
                        FROM TOMEHUB_CONTENT 
                        WHERE firebase_uid = :uid 
                          AND (normalized_content LIKE '%hayat%' OR LOWER(content_chunk) LIKE '%hayat%')
                        GROUP BY source_type
                        """,
                        {"uid": uid}
                    )
                    rows = cursor.fetchall()
                    log.write("\nDB check for 'hayat' across ALL source types:\n")
                    for st, c in rows:
                        log.write(f"  {st}: {c} rows\n")
                        
                    # Also check what source types this user has in total
                    cursor.execute(
                        "SELECT DISTINCT source_type FROM TOMEHUB_CONTENT WHERE firebase_uid = :uid",
                        {"uid": uid}
                    )
                    log.write("\nAll source types this user has:\n")
                    for (st,) in cursor.fetchall():
                        log.write(f"  - {st}\n")
                        
        except Exception as e:
            log.write(f"DB Error: {e}\n")

    print("Done logging to debug_hayat.log")

if __name__ == "__main__":
    debug_hayat()
