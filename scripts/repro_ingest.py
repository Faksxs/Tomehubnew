import os
import sys
from dotenv import load_dotenv

# Add apps/backend and apps/backend/services to path
backend_dir = os.path.join(os.getcwd(), 'apps', 'backend')
sys.path.append(backend_dir)
sys.path.append(os.path.join(backend_dir, 'services'))

from services.ingestion_service import ingest_book

# Mock temp file (even if it's empty, it should fail at extraction, but not 500 unless code is wrong)
temp_file = "test.pdf"
with open(temp_file, "w") as f:
    f.write("%PDF-1.4 test")

try:
    print("Testing ingest_book...")
    # Using Orwell's 1984 as in the user's error
    result = ingest_book(temp_file, "1984", "George Orwell", "vpq1p0UzcCSLAh1d18WgZZWPBE63")
    print(f"Result: {result}")
finally:
    if os.path.exists(temp_file):
        os.remove(temp_file)
