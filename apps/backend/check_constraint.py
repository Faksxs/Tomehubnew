
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.db_manager import DatabaseManager

def check_constraint():
    DatabaseManager.init_pool()
    
    with DatabaseManager.get_connection() as conn:
        with conn.cursor() as cursor:
            # Query constraint definition
            print("\n--- CONSTRAINT DEFINITION ---")
            cursor.execute("SELECT search_condition_vc FROM user_constraints WHERE constraint_name = 'SYS_C0029986'")
            row = cursor.fetchone()
            if row:
                print(f"Condition: {row[0]}")
            else:
                print("Constraint not found in user_constraints (might be system generated name on different schema? or need UPPER case?)")
                # Try listing all check constraints on table
                cursor.execute("SELECT constraint_name, search_condition_vc FROM user_constraints WHERE table_name = 'TOMEHUB_CONTENT' AND constraint_type = 'C'")
                for r in cursor.fetchall():
                    print(f"[{r[0]}] {r[1]}")

if __name__ == "__main__":
    check_constraint()
