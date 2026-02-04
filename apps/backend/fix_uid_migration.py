
from infrastructure.db_manager import DatabaseManager

def fix_migration():
    bad_uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    good_uid = "vpq1p0UzcCSLAhId18WgZ2wPBE63"
    
    print(f"Migrating from BAD: {bad_uid}")
    print(f"            to GOOD: {good_uid}")
    
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Update TOMEHUB_CONTENT
                cursor.execute(
                    "UPDATE TOMEHUB_CONTENT SET firebase_uid = :good WHERE firebase_uid = :bad",
                    {"good": good_uid, "bad": bad_uid}
                )
                print(f"Updated {cursor.rowcount} rows in TOMEHUB_CONTENT")
                
                # 2. Try updating TOMEHUB_BOOKS (ignore error if missing)
                try:
                    cursor.execute(
                        "UPDATE TOMEHUB_BOOKS SET firebase_uid = :good WHERE firebase_uid = :bad",
                        {"good": good_uid, "bad": bad_uid}
                    )
                    print(f"Updated {cursor.rowcount} rows in TOMEHUB_BOOKS")
                except Exception as e:
                    print(f"Skipping TOMEHUB_BOOKS update (might not exist): {e}")

                conn.commit()
                
                # Verify
                cursor.execute("SELECT COUNT(*) FROM TOMEHUB_CONTENT WHERE firebase_uid = :bad", {"bad": bad_uid})
                remaining = cursor.fetchone()[0]
                print(f"Remaining bad rows: {remaining}")

    except Exception as e:
        print(f"Migration Error: {e}")

if __name__ == "__main__":
    fix_migration()
