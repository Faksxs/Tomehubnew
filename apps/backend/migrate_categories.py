
import os
import json
import logging
import asyncio
import google.generativeai as genai
from typing import List, Dict, Any
from dotenv import load_dotenv

# Add backend dir to path for imports
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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

# Define Target Categories
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
4. If no categories fit perfectly, pick the closest one or "Sosyoloji" (as a broad social catch-all if applicable).
5. Prefer Turkish category names from the list provided.

Return ONLY valid JSON: ["Category1", "Category2"]
"""

async def get_categories_for_book(title: str, tags: List[str]) -> List[str]:
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = PROMPT_CATEGORIZE.format(
            categories_list=", ".join(CATEGORIES),
            title=title,
            tags=", ".join(tags)
        )
        
        response = await asyncio.to_thread(model.generate_content, prompt)
        text = response.text.strip()
        
        # Clean JSON
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
            
        return json.loads(text.strip())
    except Exception as e:
        logger.error(f"AI categorization failed for {title}: {e}")
        return ["Sosyoloji"] # Default fallback

async def migrate():
    DatabaseManager.init_pool()
    
    try:
        conn = DatabaseManager.get_connection()
        try:
            cursor = conn.cursor()
            
            # 1. Add Column if not exists
            try:
                logger.info("Adding CATEGORIES column to TOMEHUB_CONTENT...")
                cursor.execute("ALTER TABLE TOMEHUB_CONTENT ADD (CATEGORIES VARCHAR2(500))")
                conn.commit()
                logger.info("Column added successfully.")
            except Exception as e:
                if "ORA-01430" in str(e): # Column already exists
                    logger.info("CATEGORIES column already exists.")
                else:
                    logger.error(f"Failed to add column: {e}")
                    
            # 2. Identify Unique Books needing categorization
            cursor.execute("SELECT DISTINCT BOOK_ID, TITLE FROM TOMEHUB_CONTENT WHERE CATEGORIES IS NULL AND SOURCE_TYPE IN ('PDF', 'EPUB', 'PDF_CHUNK')")
            books_to_categorize = cursor.fetchall()
            logger.info(f"Found {len(books_to_categorize)} unique books to categorize.")
            
            for book_id, full_title in books_to_categorize:
                cursor.execute("SELECT CONTENT_CHUNK FROM TOMEHUB_CONTENT WHERE BOOK_ID = :bid AND CHUNK_INDEX = 0", {"bid": book_id})
                chunk_row = cursor.fetchone()
                tags = []
                if chunk_row:
                    content = safe_read_clob(chunk_row[0])
                    for line in content.split('\n'):
                        if line.startswith("Tags:"):
                            tags = [t.strip() for t in line.replace("Tags:", "").split(',') if t.strip()]
                            break
                
                selected_categories = await get_categories_for_book(full_title, tags)
                cat_string = ",".join(selected_categories)
                
                logger.info(f"Book: {full_title} -> Categories: {cat_string}")
                
                cursor.execute(
                    "UPDATE TOMEHUB_CONTENT SET CATEGORIES = :p_cats WHERE BOOK_ID = :p_bid",
                    {"p_cats": cat_string, "p_bid": book_id}
                )
                conn.commit()
                await asyncio.sleep(0.5)
                
            logger.info("Migration complete.")
        finally:
            conn.close() # CRITICAL: Close connection
        
    except Exception as e:
        logger.error(f"Migration error: {e}")
    finally:
        DatabaseManager.close_pool()

if __name__ == "__main__":
    asyncio.run(migrate())
