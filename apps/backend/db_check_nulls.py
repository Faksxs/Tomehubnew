import os, sys
CURRENT_DIR = os.getcwd()
sys.path.insert(0, CURRENT_DIR)
from infrastructure.db_manager import DatabaseManager

def check_nulls():
    DatabaseManager.init_pool()
    try:
        with DatabaseManager.get_read_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = 'TOMEHUB_LIBRARY_ITEMS'")
                columns = [row[0] for row in cur.fetchall()]
                
                cur.execute("SELECT COUNT(*) FROM TOMEHUB_LIBRARY_ITEMS")
                total_rows = cur.fetchone()[0]
                
                null_report = []
                for col in columns:
                    cur.execute(f"SELECT COUNT(*) FROM TOMEHUB_LIBRARY_ITEMS WHERE {col} IS NULL")
                    null_count = cur.fetchone()[0]
                    if null_count > 0:
                        null_report.append((col, null_count))
                
                null_report.sort(key=lambda x: x[1], reverse=True)
                
                with open('report_ascii.txt', 'w', encoding='utf-8') as f:
                    f.write(f"Total Rows: {total_rows}\\n\\n")
                    for col, count in null_report:
                        f.write(f"{col}: {count} NULLs ({(count/total_rows)*100:.1f}%)\\n")

    finally:
        DatabaseManager.close_pool()

if __name__ == '__main__':
    check_nulls()
