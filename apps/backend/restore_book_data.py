
import sys
import os
import json
import datetime

# Add current directory and apps/backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from infrastructure.db_manager import DatabaseManager

def restore_book():
    DatabaseManager.init_pool()
    target_id = "1763947192884s1obi7m9k"
    
    try:
        with DatabaseManager.get_write_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Check if already exists in active tables
                cursor.execute("SELECT count(*) FROM TOMEHUB_LIBRARY_ITEMS WHERE ITEM_ID = :tid", tid=target_id)
                if cursor.fetchone()[0] > 0:
                    print(f"Book {target_id} already exists in TOMEHUB_LIBRARY_ITEMS.")
                else:
                    print(f"Fetching library info for {target_id}...")
                    cursor.execute("SELECT TITLE, AUTHOR, FIREBASE_UID, CREATED_AT FROM TOMEHUB_BOOKS_ARCHIVED WHERE ID = :tid", tid=target_id)
                    row = cursor.fetchone()
                    if row:
                        title, author, uid, created_at = row
                        print(f"Restoring book: {title}")
                        # Minimal insert to test
                        cursor.execute("""
                            INSERT INTO TOMEHUB_LIBRARY_ITEMS 
                            (ITEM_ID, FIREBASE_UID, ITEM_TYPE, TITLE, AUTHOR, IS_DELETED, IS_PLACEHOLDER, CREATED_AT, UPDATED_AT, ROW_VERSION)
                            VALUES (:v_tid, :v_uid, 'BOOK', :v_title, :v_author, 0, 0, :v_cat, :v_uat, 1)
                        """, v_tid=target_id, v_uid=uid, v_title=title, v_author=author, v_cat=created_at, v_uat=datetime.datetime.now())
                    else:
                        print(f"Error: {target_id} not in archive.")
                        return

                # 2. Restore Content 
                cursor.execute("SELECT count(*) FROM TOMEHUB_CONTENT_V2 WHERE ITEM_ID = :tid", tid=target_id)
                if cursor.fetchone()[0] > 0:
                    print(f"Content for {target_id} exists.")
                else:
                    print(f"Restoring content for {target_id}...")
                    cursor.execute("""
                        SELECT BOOK_ID, FIREBASE_UID, NVL(CONTENT_TYPE, 'BOOK_CHUNK'), TITLE, CONTENT_CHUNK, 
                               PAGE_NUMBER, CHUNK_INDEX, CREATED_AT, UPDATED_AT, NORMALIZED_CONTENT
                        FROM TOMEHUB_CONTENT_ARCHIVED
                        WHERE BOOK_ID = :tid
                    """, tid=target_id)
                    
                    rows = cursor.fetchall()
                    restored_count = 0
                    for r in rows:
                        book_id, uid, ctype, title, chunk, pnum, cidx, cat, uat, norm = r
                        chunk_text = chunk.read() if hasattr(chunk, 'read') else str(chunk)
                        
                        # Use very specific non-reserved bind names
                        sql = """
                            INSERT INTO TOMEHUB_CONTENT_V2 
                            (ITEM_ID, FIREBASE_UID, CONTENT_TYPE, TITLE, CONTENT_CHUNK, PAGE_NUMBER, CHUNK_INDEX, CREATED_AT, UPDATED_AT, NORMALIZED_CONTENT)
                            VALUES (:b_id, :f_uid, :c_type, :t_title, :c_chunk, :p_num, :c_idx, :c_at, :u_at, :n_content)
                        """
                        cursor.execute(sql, {
                            "b_id": book_id,
                            "f_uid": uid,
                            "c_type": ctype,
                            "t_title": title,
                            "c_chunk": chunk_text,
                            "p_num": pnum,
                            "c_idx": cidx,
                            "c_at": cat,
                            "u_at": uat,
                            "n_content": norm
                        })
                        restored_count += 1
                    
                    print(f"Restored {restored_count} content records.")

                conn.commit()
                print("Commit successful.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    restore_book()
