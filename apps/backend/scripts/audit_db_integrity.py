
import sys
import os
import time

# Add backend directory to sys.path to allow imports
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
sys.path.insert(0, backend_dir)

from infrastructure.db_manager import DatabaseManager
from config import settings

def audit_integrity():
    print("=== Database Integrity Audit Starting ===")
    print(f"Connecting to DB: {settings.DB_USER}@{settings.DB_DSN}")

    try:
        DatabaseManager.init_pool()
        conn = DatabaseManager.get_read_connection()
        cursor = conn.cursor()
        
        # 1. Get all user tables
        print("\n--- Scanning Tables ---")
        cursor.execute("SELECT table_name FROM user_tables ORDER BY table_name")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Found {len(tables)} tables: {', '.join(tables)}")

        # 2. Find potential FK columns (ending in _ID)
        potential_fks = []
        for table in tables:
            cursor.execute(f"SELECT column_name FROM user_tab_cols WHERE table_name = :1 AND column_name LIKE '%_ID'", [table])
            cols = [row[0] for row in cursor.fetchall()]
            for col in cols:
                # heuristic: ignore ID column of the table itself if it matches TABLE_ID
                # usually PK is just ID or TABLE_ID.
                potential_fks.append((table, col))

        # 3. Get actual FKs
        cursor.execute("""
            SELECT ucc.table_name, ucc.column_name 
            FROM user_cons_columns ucc
            JOIN user_constraints uc ON ucc.constraint_name = uc.constraint_name
            WHERE uc.constraint_type = 'R'
        """)
        actual_fks = set((row[0], row[1]) for row in cursor.fetchall())

        # 4. Identify Missing FKs
        missing_fks = []
        print("\n--- Checking Foreign Key Constraints ---")
        for table, col in potential_fks:
            if (table, col) not in actual_fks:
                # Filter out likely PKs (e.g., ID column)
                if col == "ID": 
                    continue
                    
                # Heuristic: verify if it looks like a parent reference
                # e.g. BOOK_ID -> TOMEHUB_BOOKS?
                print(f"[!] Potential missing FK: {table}.{col}")
                missing_fks.append((table, col))

        # 5. Check for Orphans
        print("\n--- Checking for Orphaned Records ---")
        orphans_report = []
        
        for table, col in missing_fks:
            # Guess parent table
            parent_guess = None
            if col == "BOOK_ID":
                parent_guess = "TOMEHUB_BOOKS"
            elif col == "USER_ID" or col == "FIREBASE_UID":
                # User table might not exist in oracle if managed by Firebase
                # But let's check if there is a USERS table
                if "USERS" in tables: parent_guess = "USERS"
                elif "TOMEHUB_USERS" in tables: parent_guess = "TOMEHUB_USERS"
            elif col.endswith("_ID"):
                # try removing _ID and pluralizing? 
                # naive guess
                pass
            
            if parent_guess and parent_guess in tables:
                query = f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL AND {col} NOT IN (SELECT ID FROM {parent_guess})"
                try:
                    cursor.execute(query)
                    count = cursor.fetchone()[0]
                    if count > 0:
                        msg = f"CRITICAL: {table}.{col} has {count} orphans (Parent: {parent_guess})"
                        print(msg)
                        orphans_report.append({
                            "table": table,
                            "column": col, 
                            "parent": parent_guess,
                            "orphans": count,
                            "query": f"SELECT * FROM {table} WHERE {col} IS NOT NULL AND {col} NOT IN (SELECT ID FROM {parent_guess})"
                        })
                    else:
                        print(f"OK: {table}.{col} matches {parent_guess} (0 orphans)")
                except Exception as e:
                    print(f"Error checking {table}.{col}: {e}")
            else:
                print(f"SKIP: Could not determine parent for {table}.{col}")

        # 6. Generate Report
        report_path = "audit_report_db.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# Database Integrity Audit Report\n\n")
            f.write("## 1. Missing Constraints\n")
            for table, col in missing_fks:
                f.write(f"- **{table}.{col}** (No visible Foreign Key)\n")
            
            f.write("\n## 2. Orphaned Records\n")
            if orphans_report:
                for item in orphans_report:
                    f.write(f"### {item['table']}.{item['column']}\n")
                    f.write(f"- **Orphans:** {item['orphans']}\n")
                    f.write(f"- **Parent Table:** {item['parent']}\n")
                    f.write(f"- **Detection Query:** `{item['query']}`\n")
                    f.write(f"- **Cleanup Strategy:** [ACTION REQUIRED]\n\n")
            else:
                f.write("No orphaned records found for identified potential FKs.\n")

        print(f"\nReport generated at {report_path}")


    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            if 'cursor' in locals() and cursor:
                cursor.close()
            if 'conn' in locals() and conn:
                conn.close()
        except Exception as e:
             print(f"Error closing connection: {e}")
        
        try:
            DatabaseManager.close_pool()
        except Exception as e:
            print(f"Error closing pool: {e}")

if __name__ == "__main__":
    audit_integrity()
