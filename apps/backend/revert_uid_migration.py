
from infrastructure.db_manager import DatabaseManager

def revert_migration():
    # The MANGLED UID I created
    bad_mangled_uid = "vpq1p0UzcCSLAhId18WgZ2wPBE63"
    # The ACTUAL UID from the user's browser screenshot
    real_session_uid = "vpq1p0UzcCSLAh1d18WgZZWPBE63"
    
    print(f"Reverting from MANGLED: {bad_mangled_uid}")
    print(f"            to REAL:   {real_session_uid}")
    
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Update TOMEHUB_CONTENT
                cursor.execute(
                    "UPDATE TOMEHUB_CONTENT SET firebase_uid = :real WHERE firebase_uid = :mangled",
                    {"real": real_session_uid, "mangled": bad_mangled_uid}
                )
                print(f"Reverted {cursor.rowcount} rows in TOMEHUB_CONTENT")
                
                # 2. Update TOMEHUB_BOOKS (if exists)
                try:
                    cursor.execute(
                        "UPDATE TOMEHUB_BOOKS SET firebase_uid = :real WHERE firebase_uid = :mangled",
                        {"real": real_session_uid, "mangled": bad_mangled_uid}
                    )
                    print(f"Reverted {cursor.rowcount} rows in TOMEHUB_BOOKS")
                except Exception as e:
                    print(f"Skipping TOMEHUB_BOOKS (error expected if table missing): {e}")

                conn.commit()
                print("Revert complete.")

    except Exception as e:
        print(f"Revert Error: {e}")

if __name__ == "__main__":
    revert_migration()
