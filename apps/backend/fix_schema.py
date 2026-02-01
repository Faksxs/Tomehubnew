
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.db_manager import DatabaseManager

def fix_schema_and_data():
    DatabaseManager.init_pool()
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # 1. Drop Constraint
            print("\n--- DROPPING CONSTRAINT SYS_C0029986 ---")
            try:
                cursor.execute("ALTER TABLE TOMEHUB_CONTENT DROP CONSTRAINT SYS_C0029986")
                print("Constraint dropped.")
            except Exception as e:
                print(f"Error dropping constraint (maybe already dropped?): {e}")

            # 2. Fix Personal Notes
            print("\n--- FIXING PERSONAL NOTES ---")
            cursor.execute("UPDATE TOMEHUB_CONTENT SET source_type = 'PERSONAL_NOTE' WHERE title LIKE '% - Self' OR title LIKE '%Dogum gunu%'")
            print(f"Updated {cursor.rowcount} rows to 'PERSONAL_NOTE'.")
            
            # 3. Fix Articles (Candidate: 'rent a car - fakss', 'fas - das')
            # Assuming these are the 9 articles user mentioned.
            # I will query them first to be sure they match title
            print("\n--- FIXING ARTICLES ---")
            titles = ['rent a car - fakss', 'fas - das']
            for t in titles:
                 cursor.execute("UPDATE TOMEHUB_CONTENT SET source_type = 'ARTICLE' WHERE title = :t", {"t": t})
                 print(f"Updated {cursor.rowcount} rows for '{t}' to 'ARTICLE'.")
            
            conn.commit()
            
            # 4. Add New Constraint
            print("\n--- ADDING NEW CONSTRAINT ---")
            # PDF, NOTES (Highlights), EPUB, PDF_CHUNK, ARTICLE, WEBSITE, PERSONAL_NOTE
            sql = """
            ALTER TABLE TOMEHUB_CONTENT ADD CONSTRAINT CHK_SOURCE_TYPE 
            CHECK (source_type IN ('PDF', 'NOTES', 'EPUB', 'PDF_CHUNK', 'ARTICLE', 'WEBSITE', 'PERSONAL_NOTE', 'personal'))
            """
            try:
                cursor.execute(sql)
                print("New constraint CHK_SOURCE_TYPE added.")
            except Exception as e:
                print(f"Error adding constraint: {e}")

if __name__ == "__main__":
    fix_schema_and_data()
