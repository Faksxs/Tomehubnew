# -*- coding: utf-8 -*-
import os
import json
import asyncio
import logging
from typing import List, Optional, Dict, Any
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

from services.monitoring import AI_SERVICE_LATENCY

# Constants for Prompts (Replicated from geminiService.ts)
PROMPT_ENRICH_BOOK = """
Enrich this book data with missing details (summary, tags, publisher, publication year, page count).

Current Data:
{json_data}

CRITICAL LANGUAGE INSTRUCTION:
1. DETECT the language of the book TITLE and AUTHOR.
2. IF the book is clearly English (e.g., 'The Great Gatsby'), generate 'summary' and 'tags' in ENGLISH.
3. IF the book is Turkish (e.g., 'Hayatın Anlamı', 'Sabahattin Ali') OR the language is ambiguous, generate 'summary' and 'tags' in TURKISH. 
4. DO NOT mix languages. For a Turkish book, the summary and ALL tags must be in Turkish.

Return the COMPLETE updated JSON object.
- Ensure 'summary' is detailed (at least 3 sentences).
- Ensure 'tags' has at least 3 relevant genres/topics.
- Do NOT change the title or author if they look correct.
- For 'translator' and 'pageCount', return 'null' if you are purely guessing.

INCLUDE a 'confidence_scores' object in your JSON response:
{{
  "translator": "high" | "medium" | "low",
  "pageCount": "high" | "medium" | "low"
}}

Return ONLY valid JSON. No markdown.
"""

PROMPT_GENERATE_TAGS = """
Generate 3-5 relevant tags for this note. 
CRITICAL: The tags MUST be in the same language as the note content (e.g., if note is Turkish, tags must be Turkish).
Return ONLY a JSON array of strings.

Note: "{note_content}"
"""

PROMPT_VERIFY_COVER = """
Find a valid high-quality book cover image URL for:
Title: {title}
Author: {author}
ISBN: {isbn}

Return ONLY the URL string. If not found, return "null".
"""

PROMPT_ANALYZE_HIGHLIGHTS = """
Analyze these book highlights and provide a concise summary of the key themes and insights.
CRITICAL: The summary MUST be in the same language as the highlights (Default to Turkish if mixed).

{highlights_text}

Return ONLY the summary text.
"""

PROMPT_SEARCH_RESOURCES = """
I need to find book or article recommendations based on this query: "{query}".
Type: {resource_type}

Please return a JSON array of items. Each item should have:
- title
- author
- publisher
- isbn (if book)
- summary (brief)
- publishedDate (year)
- url (if website/article)
- pageCount (number, if book)

Return ONLY valid JSON. No markdown formatting.
"""

# Helper to clean JSON markdown
def clean_json_response(text: str) -> str:
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return text.strip()

# --- Async AI Functions with Tenacity ---

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry_error_callback=lambda state: state.args[0] if state.args else {} # Return original data (arg 0) on failure
)
async def enrich_book_async(book_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enriches book metadata using Gemini.
    """
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = PROMPT_ENRICH_BOOK.format(json_data=json.dumps(book_data, ensure_ascii=False))
        
        with AI_SERVICE_LATENCY.labels(service="gemini_flash", operation="generate").time():
            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, prompt), 
                timeout=30.0
            )
        text = response.text
        
        try:
            clean_text = clean_json_response(text)
            enriched_data = json.loads(clean_text)
            
            # Observability: Check confidence scores for "Risky" fields (Type B/C)
            if 'confidence_scores' in enriched_data:
                scores = enriched_data['confidence_scores']
                
                # Type C: Estimated Metadata (High Risk)
                if enriched_data.get('pageCount') and scores.get('pageCount') == 'low':
                    logger.warning(f"[AI AIKIDO] Low confidence pageCount estimated for '{book_data.get('title')}': {enriched_data['pageCount']}")
                    
                # Type B: Inferred Metadata (Medium Risk)
                if enriched_data.get('translator') and scores.get('translator') == 'low':
                    logger.info(f"[AI AIKIDO] Low confidence translator inferred for '{book_data.get('title')}': {enriched_data['translator']}")
            
            # Merge ensures we don't lose original fields if AI omits them
            return {**book_data, **enriched_data}
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parse Error for Enrichment. Raw text: {text[:500]}... Error: {e}")
            raise e # Retry might fix bad JSON
            
    except Exception as e:
        logger.error(f"Enrichment failed: {e}")
        raise e # Let Tenacity retry

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
async def generate_tags_async(note_content: str) -> List[str]:
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = PROMPT_GENERATE_TAGS.format(note_content=note_content)
        
        with AI_SERVICE_LATENCY.labels(service="gemini_flash", operation="generate").time():
            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, prompt), 
                timeout=30.0
            )
        text = clean_json_response(response.text)
        
        return json.loads(text)
    except Exception as e:
        logger.error(f"Tag gen failed: {e}")
        raise e

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
async def verify_cover_async(title: str, author: str, isbn: str = "") -> Optional[str]:
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = PROMPT_VERIFY_COVER.format(title=title, author=author, isbn=isbn or 'N/A')
        
        with AI_SERVICE_LATENCY.labels(service="gemini_flash", operation="generate").time():
            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, prompt), 
                timeout=20.0
            )
        url = response.text.strip()
        
        if url.lower() == "null" or "http" not in url:
            return None
        return url
    except Exception as e:
        logger.error(f"Cover verify failed: {e}")
        raise e

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
async def analyze_highlights_async(highlights: List[str]) -> str:
    try:
        if not highlights:
            return ""
            
        model = genai.GenerativeModel('gemini-2.0-flash')
        text_block = "\n---\n".join(highlights)
        prompt = PROMPT_ANALYZE_HIGHLIGHTS.format(highlights_text=text_block)
        
        with AI_SERVICE_LATENCY.labels(service="gemini_flash", operation="generate").time():
            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, prompt), 
                timeout=35.0
            )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Highlight analysis failed: {e}")
        raise e

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
async def search_resources_async(query: str, resource_type: str) -> List[Dict[str, Any]]:
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = PROMPT_SEARCH_RESOURCES.format(query=query, resource_type=resource_type)
        
        with AI_SERVICE_LATENCY.labels(service="gemini_flash", operation="generate").time():
            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, prompt), 
                timeout=30.0
            )
        clean = clean_json_response(response.text)
        return json.loads(clean)
    except Exception as e:
        logger.error(f"Resource search failed: {e}")
        raise e

PROMPT_EXTRACT_METADATA = """
Analyze the following text (from the first page of a document) and extract the Book Title and Author.

Text:
"{text}"

Return ONLY a JSON object with keys: "title", "author".
If unsure, return null for that field.
"""

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
async def extract_metadata_from_text_async(text: str) -> Dict[str, Optional[str]]:
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        # Truncate text to avoid token limits (first 2000 chars is usually enough for title page)
        prompt = PROMPT_EXTRACT_METADATA.format(text=text[:2000])
        
        with AI_SERVICE_LATENCY.labels(service="gemini_flash", operation="generate").time():
            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, prompt), 
                timeout=25.0
            )
        clean = clean_json_response(response.text)
        return json.loads(clean)
    except Exception as e:
        logger.error(f"Metadata extraction failed: {e}")
        return {"title": None, "author": None}


# --- Batch Streaming Logic ---

async def stream_enrichment(books: List[Dict[str, Any]], max_total_bytes: int = 1048576):
    """
    Generator that yields SSE (Server-Sent Events) data for each enriched book.
    Includes a safety limit on total volume for backpressure control.
    """
    total_bytes_sent = 0
    for book in books:
        try:
            # Enrich one book
            enriched = await enrich_book_async(book)
            chunk = json.dumps(enriched, ensure_ascii=False) + "\n"
        except Exception as e:
            # If failed, yield original with error flag
            book['error'] = str(e)
            chunk = json.dumps(book, ensure_ascii=False) + "\n"
        
        chunk_bytes = len(chunk.encode('utf-8'))
        if total_bytes_sent + chunk_bytes > max_total_bytes:
            logger.warning(f"Stream volume limit reached ({max_total_bytes}). Closing stream.")
            yield json.dumps({"status": "limit_reached", "message": "Maximum stream volume exceeded"}) + "\n"
            break
            
        yield chunk
        total_bytes_sent += chunk_bytes
        
        # Small delay to prevent rate limit spikes
        await asyncio.sleep(0.5)
