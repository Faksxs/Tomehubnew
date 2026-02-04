import io
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from infrastructure.db_manager import DatabaseManager

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

def merge_duplicates():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # Ensure serial DML to avoid ORA-12860 sibling row lock deadlocks
                try:
                    cursor.execute("ALTER SESSION DISABLE PARALLEL DML")
                except Exception as e:
                    print(f"WARN: Could not disable parallel DML: {e}")
                try:
                    cursor.execute("ALTER SESSION SET PARALLEL_DEGREE_POLICY = MANUAL")
                except Exception as e:
                    print(f"WARN: Could not set PARALLEL_DEGREE_POLICY: {e}")

                # Lock tables to avoid deadlocks during merge
                cursor.execute("LOCK TABLE TOMEHUB_CONCEPTS IN EXCLUSIVE MODE")
                cursor.execute("LOCK TABLE TOMEHUB_CONCEPT_CHUNKS IN EXCLUSIVE MODE")
                cursor.execute("LOCK TABLE TOMEHUB_RELATIONS IN EXCLUSIVE MODE")

                cursor.execute("""
                    SELECT LOWER(name) AS name_lower
                    FROM TOMEHUB_CONCEPTS
                    GROUP BY LOWER(name)
                    HAVING COUNT(*) > 1
                """)
                groups = [r[0] for r in cursor.fetchall()]

                if not groups:
                    print("NO_DUPLICATES")
                    conn.commit()
                    return

                for name_lower in groups:
                    retries = 3
                    while retries > 0:
                        try:
                            cursor.execute("""
                                SELECT id, name, description
                                FROM TOMEHUB_CONCEPTS
                                WHERE LOWER(name) = :p_name
                                ORDER BY id ASC
                                FOR UPDATE
                            """, {"p_name": name_lower})
                            rows = cursor.fetchall()
                            if len(rows) < 2:
                                break

                            keep_id = rows[0][0]
                            keep_desc = rows[0][2]
                            duplicate_ids = [r[0] for r in rows[1:]]

                            # Merge description if missing on keeper
                            if keep_desc is None:
                                for r in rows[1:]:
                                    if r[2]:
                                        cursor.execute("""
                                            UPDATE TOMEHUB_CONCEPTS
                                            SET DESCRIPTION = :p_desc
                                            WHERE ID = :p_id
                                        """, {"p_desc": r[2], "p_id": keep_id})
                                        break

                            ids_csv = ",".join([str(i) for i in duplicate_ids])
                            # Re-point concept chunks
                            cursor.execute(f"""
                                UPDATE TOMEHUB_CONCEPT_CHUNKS
                                SET CONCEPT_ID = :p_keep
                                WHERE CONCEPT_ID IN ({ids_csv})
                            """, {"p_keep": keep_id})

                            # Re-point relations (src/dst)
                            cursor.execute(f"""
                                UPDATE TOMEHUB_RELATIONS
                                SET SRC_ID = :p_keep
                                WHERE SRC_ID IN ({ids_csv})
                            """, {"p_keep": keep_id})
                            cursor.execute(f"""
                                UPDATE TOMEHUB_RELATIONS
                                SET DST_ID = :p_keep
                                WHERE DST_ID IN ({ids_csv})
                            """, {"p_keep": keep_id})

                            # Delete duplicates
                            cursor.execute(f"""
                                DELETE FROM TOMEHUB_CONCEPTS
                                WHERE ID IN ({ids_csv})
                            """)

                            conn.commit()
                            print(f"MERGED: {name_lower} -> kept {keep_id}, removed {duplicate_ids}")
                            break
                        except Exception as e:
                            conn.rollback()
                            retries -= 1
                            if retries == 0:
                                raise
                            print(f"Retrying merge for {name_lower} after error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    merge_duplicates()
