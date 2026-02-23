
import sys
import os
sys.path.append(os.getcwd())

import logging
from infrastructure.db_manager import DatabaseManager
from services.report_service import generate_file_report

# Setup logging to see output
logging.basicConfig(level=logging.INFO)

def verify_report():
    print("--- Report Generation Verification ---")
    
    # Get a real book ID
    with DatabaseManager.get_read_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT BOOK_ID, FIREBASE_UID, TITLE FROM TOMEHUB_BOOKS FETCH FIRST 1 ROWS ONLY")
        row = cursor.fetchone()
        
    if not row:
        print("✗ No books found in database to test with.")
        return
        
    book_id, uid, title = row
    print(f"Testing with Book: {title} (ID: {book_id})")
    
    try:
        # Run the report generation
        success = generate_file_report(book_id, uid)
    except Exception:
        import traceback
        traceback.print_exc()
        success = False
    
    if success:
        print(f"✓ SUCCESS: Report generated for {title}")
        # Verify saved data
        with DatabaseManager.get_read_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT SUMMARY_TEXT FROM TOMEHUB_FILE_REPORTS WHERE BOOK_ID = :p_bid", {"p_bid": book_id})
            result = cursor.fetchone()
            if result:
                print("✓ Data successfully saved to TOMEHUB_FILE_REPORTS.")
                print("Content Preview:")
                print(result[0] if isinstance(result[0], str) else result[0].read()[:500] + "...")
    else:
        print(f"✗ FAILURE: Report generation failed for {title}")

if __name__ == "__main__":
    verify_report()
