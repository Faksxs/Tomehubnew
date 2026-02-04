
import os
import sys

# Add parent directory to path to allow importing from main app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.db_manager import DatabaseManager

def delete_pdf_records():
    print("🚀 Starting PDF Record Cleanup...")
    
    try:
        DatabaseManager.init_pool()
        
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Check what we have
                cursor.execute("""
                    SELECT source_type, COUNT(*) 
                    FROM TOMEHUB_CONTENT 
                    WHERE source_type IN ('PDF', 'EPUB', 'PDF_CHUNK')
                    GROUP BY source_type
                """)
                rows = cursor.fetchall()
                
                if not rows:
                    print("✅ No PDF records found. Database is already clean.")
                    return

                print("\n📊 Current PDF Records:")
                total_count = 0
                for r in rows:
                    print(f"   - {r[0]}: {r[1]} records")
                    total_count += r[1]
                
                print(f"\n⚠️  About to DELETE {total_count} records.")
                
                # 2. Execute Delete
                cursor.execute("""
                    DELETE FROM TOMEHUB_CONTENT 
                    WHERE source_type IN ('PDF', 'EPUB', 'PDF_CHUNK')
                """)
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                print(f"\n✅ Successfully deleted {deleted_count} records.")
                
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    delete_pdf_records()
