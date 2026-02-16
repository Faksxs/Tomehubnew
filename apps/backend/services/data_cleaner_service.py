
import os
import re
from typing import List, Optional
from dotenv import load_dotenv
from services.llm_client import MODEL_TIER_FLASH, generate_text, get_model_for_tier

# Load environment
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

class DataCleanerService:
    """
    Service to remove repetitive metadata, ISBNs, and headers/footers from content.
    """
    
    @staticmethod
    def strip_basic_patterns(text: str) -> str:
        """
        Fast regex-based cleaning for common artifacts.
        """
        if not text:
            return ""
            
        # 1. Remove ISBNs
        text = re.sub(r'ISBN(?:-10|-13)?:\s*[\d\-X]+', '', text, flags=re.IGNORECASE)
        
        # 2. Remove common URLs
        text = re.sub(r'www\.[a-z0-9\-]+\.[a-z]{2,}(?:\.[a-z]{2,})?', '', text, flags=re.IGNORECASE)
        
        # 3. Remove consecutive spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    @staticmethod
    def clean_with_ai(text: str, title: str = "", author: str = "") -> str:
        """
        Deep cleaning using Gemini to remove book headers/footers.
        """
        if not GEMINI_API_KEY or not text or len(text) < 50:
            return text
            
        prompt = f"""
        TASK: Remove redundant metadata, headers, footers, ISBN numbers, and repeated book titles/authors from the text below.
        CONTEXT: 
        - Title: {title}
        - Author: {author}
        
        INSTRUCTIONS:
        - Keep the ACTUAL content/body of the text.
        - Strip "junk" like page numbers, publisher names (e.g. "METIS YAYINLARI"), and repeating title strings.
        - CRITICAL: Remove any BIBLIOGRAPHY, REFERENCES, or INDEX lists if they appear. (e.g. Lists of authors, years, cities).
        - Do not summarize or change the tone. Just strip the clutter.
        - Return ONLY the cleaned text.

        TEXT TO CLEAN:
        ---
        {text}
        ---
        
        CLEANED TEXT:
        """
        
        try:
            model = get_model_for_tier(MODEL_TIER_FLASH)
            result = generate_text(
                model=model,
                prompt=prompt,
                task="data_cleaner",
                model_tier=MODEL_TIER_FLASH,
                timeout_s=20.0,
            )
            if result and result.text:
                return result.text.strip()
        except Exception:
            pass
            
        return text
