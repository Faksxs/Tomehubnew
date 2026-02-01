
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.db_manager import DatabaseManager

def fix_and_audit():
    DatabaseManager.init_pool()
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # 1. Fix Personal Notes
            print("\n--- FIXING PERSONAL NOTES ---")
            cursor.execute("UPDATE TOMEHUB_CONTENT SET source_type = 'PERSONAL_NOTE' WHERE title LIKE '% - Self' OR title LIKE '%Dogum gunu%'")
            print(f"Updated {cursor.rowcount} rows to 'PERSONAL_NOTE'.")
            conn.commit()
            
            # 2. Audit Remaining PDFs (Candidates for Articles)
            print("\n--- REMAINING PDF TITLES (Candidates for Articles) ---")
            # Exclude known books if possible? I'll just list distinct titles.
            cursor.execute("SELECT title, source_type, COUNT(*) FROM TOMEHUB_CONTENT WHERE source_type = 'PDF' GROUP BY title, source_type")
            for row in cursor.fetchall():
                print(f"[{row[1]}] {row[0]} ({row[2]} chunks)")

if __name__ == "__main__":
    fix_and_audit()
