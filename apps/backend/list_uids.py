
from infrastructure.db_manager import DatabaseManager

def list_uids():
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT DISTINCT firebase_uid, source_type FROM TOMEHUB_CONTENT WHERE source_type IN ('PDF', 'EPUB', 'PDF_CHUNK')")
                rows = cursor.fetchall()
                with open("uids_list.txt", "w") as f:
                    for uid, st in rows:
                        f.write(f"{uid} | {st}\n")
                print(f"Wrote {len(rows)} UIDs to uids_list.txt")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_uids()
