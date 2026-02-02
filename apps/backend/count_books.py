import oracledb
import os
from dotenv import load_dotenv
from infrastructure.db_manager import DatabaseManager

# Load env for local run
load_dotenv()

def count_books():
    print("Connecting to database...")
    report_lines = []
    try:
        DatabaseManager.init_pool()
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Total Count unique titles
                cursor.execute("SELECT COUNT(DISTINCT title) FROM TOMEHUB_CONTENT")
                total_unique = cursor.fetchone()[0]
                report_lines.append(f"Total Unique Titles in Database: {total_unique}")

                # 2. Count by Source Type
                report_lines.append("\nBreakdown by Source Type:")
                report_lines.append("-" * 30)
                query_type = """
                    SELECT source_type, COUNT(DISTINCT title) as distinct_books, COUNT(*) as total_chunks
                    FROM TOMEHUB_CONTENT
                    GROUP BY source_type
                    ORDER BY distinct_books DESC
                """
                cursor.execute(query_type)
                rows = cursor.fetchall()
                
                for source_type, distinct_books, total_chunks in rows:
                    st = source_type if source_type else "UNKNOWN"
                    report_lines.append(f"{st:<15} | {distinct_books:>5} books | {total_chunks:>6} chunks")

                # 3. List all PDF books
                report_lines.append("\nList of PDF Books found:")
                report_lines.append("-" * 60)
                query_pdf = """
                    SELECT DISTINCT title 
                    FROM TOMEHUB_CONTENT 
                    WHERE source_type = 'PDF'
                    ORDER BY title
                """
                cursor.execute(query_pdf)
                pdf_books = cursor.fetchall()
                
                if not pdf_books:
                    report_lines.append("(No PDF books found)")
                else:
                    for i, (title,) in enumerate(pdf_books, 1):
                        report_lines.append(f"{i}. {title}")
        
                # 4. List NOTES titles (to check for misclassification)
                report_lines.append("\nSample of NOTES titles:")
                report_lines.append("-" * 60)
                query_notes = """
                    SELECT DISTINCT title 
                    FROM TOMEHUB_CONTENT 
                    WHERE source_type = 'NOTES'
                    FETCH FIRST 20 ROWS ONLY
                """
                cursor.execute(query_notes)
                note_books = cursor.fetchall()
                
                if not note_books:
                    report_lines.append("(No NOTES found)")
                else:
                    for i, (title,) in enumerate(note_books, 1):
                        report_lines.append(f"{i}. {title}")
        
        # Write to file
        with open("pdf_report.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))
        print("Report saved to pdf_report.txt")
                    
    except Exception as e:
        print(f"Error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    count_books()
