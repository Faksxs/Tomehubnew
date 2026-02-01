
import os
import json
import logging
import google.generativeai as genai
from typing import List
from dotenv import load_dotenv

import sys
# Add parent dir to path
sys.path.append(os.path.join(os.getcwd()))
sys.path.append(os.path.join(os.getcwd(), 'apps', 'backend'))

from infrastructure.db_manager import DatabaseManager, safe_read_clob

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("migration")

# Load environment
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.error("GEMINI_API_KEY not found in environment!")

CATEGORIES = [
    "Felsefe", "Sosyoloji", "Politika", "Ekonomi", "Edebiyat", 
    "Roman", "Bilim", "Tarih", "İnanç", "Sanat", 
    "Psikoloji", "Kişisel Gelişim", "Aşk/İlişkiler", "Hukuk", "Eğitim"
]

PROMPT_CATEGORIZE = """
You are a library classification assistant. Categorize the given book into one OR MORE of the following predefined categories.

Predefined Categories:
{categories_list}

Book Info:
Title: {title}
Tags found in metadata: {tags}

Instructions:
1. Select only from the predefined list above.
2. You can select multiple categories (max 3) if they are truly relevant.
3. Return only a JSON array of strings. 
4. Pick the closest Turkish category names from the list.

Return ONLY valid JSON: ["Category1", "Category2"]
"""

def get_categories_for_book(title: str, tags: List[str]) -> List[str]:
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = PROMPT_CATEGORIZE.format(
            categories_list=", ".join(CATEGORIES),
            title=title,
            tags=", ".join(tags)
        )
        
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
            
        return json.loads(text.strip())
    except Exception as e:
        logger.error(f"AI categorization failed for {title}: {e}")
        return ["Sosyoloji"]

def migrate():
    DatabaseManager.init_pool()
    conn = DatabaseManager.get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Add Column
        try:
            cursor.execute("ALTER TABLE TOMEHUB_CONTENT ADD (CATEGORIES VARCHAR2(500))")
            conn.commit()
            logger.info("Column added.")
        except Exception as e:
            if "ORA-01430" in str(e):
                logger.info("Column exists.")
            else:
                logger.error(f"Alter error: {e}")
        
        # 2. Process Books
        cursor.execute("SELECT DISTINCT BOOK_ID, TITLE FROM TOMEHUB_CONTENT WHERE CATEGORIES IS NULL AND SOURCE_TYPE IN ('PDF', 'EPUB', 'PDF_CHUNK', 'NOTES') AND TITLE NOT LIKE '% - Self'")
        books = cursor.fetchall()
        logger.info(f"Processing {len(books)} unique book/notes entries...")
        
        for book_id, title in books:
            # Find tags
            cursor.execute("SELECT CONTENT_CHUNK FROM TOMEHUB_CONTENT WHERE BOOK_ID = :bid AND CHUNK_INDEX = 0", {"bid": book_id})
            row = cursor.fetchone()
            tags = []
            if row:
                content = safe_read_clob(row[0])
                for line in content.split('\n'):
                    if line.startswith("Tags:"):
                        tags = [t.strip() for t in line.replace("Tags:", "").split(',') if t.strip()]
                        break
            
            selected = get_categories_for_book(title, tags)
            cat_str = ",".join(selected)
            logger.info(f"Categorized: [{title}] -> {cat_str}")
            
            cursor.execute("UPDATE TOMEHUB_CONTENT SET CATEGORIES = :cats WHERE BOOK_ID = :bid", {"cats": cat_str, "bid": book_id})
            conn.commit()
            
        logger.info("Migration finished.")
        
    finally:
        conn.close()
        # Not explicitly closing pool to avoid potential race with background workers, process will exit anyway

if __name__ == "__main__":
    migrate()
