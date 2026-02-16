# -*- coding: utf-8 -*-
import os
import json
import asyncio
import logging
from typing import List, Optional, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

from services.llm_client import MODEL_TIER_FLASH, generate_text, get_model_for_tier
from services.language_policy_service import (
    resolve_book_content_language,
    text_matches_target_language,
    tags_match_target_language,
)

# Constants for Prompts (Replicated from geminiService.ts)
PROMPT_ENRICH_BOOK = """
Enrich this book data with missing details (summary, tags, publisher, publication year, page count).

Current Data:
{json_data}

TARGET OUTPUT LANGUAGE:
- target_language_code: {target_language_code}
- target_language_label: {target_language_label}
- force_regenerate: {force_regenerate}

LANGUAGE RULES:
1. Generate BOTH 'summary' and all 'tags' only in {target_language_label}.
2. CRITICAL: IGNORE the language of the 'Current Data' (summary/tags). 
3. BASE your output language solely on the Book Title, Author, and Publisher.
4. If the book metadata looks Turkish (e.g. Turkish Title or Publisher), output in TURKISH, even if the current summary is in English.
5. Do not change title or author.

Return the COMPLETE updated JSON object.
- Ensure 'summary' is detailed (at least 3 sentences).
- Ensure 'tags' has at least 3 relevant genres/topics.
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
CRITICAL: Each tag must be 1 to 4 words only.
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


def sanitize_generated_tags(raw_tags: Any) -> List[str]:
    """
    Enforce tag quality:
    - String tags only
    - 1..4 words per tag
    - Deduplicated (case-insensitive)
    - Max 5 tags
    """
    if not isinstance(raw_tags, list):
        return []

    clean_tags: List[str] = []
    seen = set()
    for tag in raw_tags:
        if not isinstance(tag, str):
            continue
        normalized = " ".join(tag.strip().split())
        if not normalized:
            continue
        word_count = len(normalized.split(" "))
        if word_count < 1 or word_count > 4:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        clean_tags.append(normalized)
        if len(clean_tags) >= 5:
            break
    return clean_tags


def _target_language_label(target_lang: str) -> str:
    return "TURKISH" if target_lang == "tr" else "ENGLISH"


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _language_mismatch_details(enriched_data: Dict[str, Any], target_lang: str) -> Dict[str, Any]:
    summary = str(enriched_data.get("summary") or "").strip()
    tags = enriched_data.get("tags") if isinstance(enriched_data.get("tags"), list) else []
    summary_ok = text_matches_target_language(summary, target_lang) if summary else True
    tags_ok = tags_match_target_language(tags, target_lang)
    return {
        "summary_ok": summary_ok,
        "tags_ok": tags_ok,
        "summary_present": bool(summary),
        "tags_count": len(tags),
    }


async def _run_enrich_once(
    book_data: Dict[str, Any],
    target_lang: str,
    force_regenerate: bool,
    retry_note: Optional[str] = None,
) -> Dict[str, Any]:
    model = get_model_for_tier(MODEL_TIER_FLASH)
    payload = {**book_data}
    if retry_note:
        payload["_retry_note"] = retry_note

    prompt = PROMPT_ENRICH_BOOK.format(
        json_data=json.dumps(payload, ensure_ascii=False),
        target_language_code=target_lang,
        target_language_label=_target_language_label(target_lang),
        force_regenerate=str(force_regenerate).lower(),
    )

    result = await asyncio.wait_for(
        asyncio.to_thread(
            generate_text,
            model,
            prompt,
            "ai_enrich_book",
            MODEL_TIER_FLASH,
            None,
            None,
            None,
            30.0,
        ),
        timeout=30.0,
    )

    clean_text = clean_json_response(result.text)
    enriched_data = json.loads(clean_text)
    if isinstance(enriched_data.get("tags"), list):
        enriched_data["tags"] = sanitize_generated_tags(enriched_data["tags"])
    return enriched_data


# --- Async AI Functions with Tenacity ---

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry_error_callback=lambda state: state.args[0] if state.args else {}
)
async def enrich_book_async(book_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enriches book metadata using Gemini.
    """
    try:
        language_policy = resolve_book_content_language(book_data)
        target_lang = str(language_policy.get("resolved_lang") or "tr")
        force_regenerate = _coerce_bool(book_data.get("force_regenerate"))

        enriched_data = await _run_enrich_once(book_data, target_lang, force_regenerate)
        mismatch = _language_mismatch_details(enriched_data, target_lang)

        if not (mismatch["summary_ok"] and mismatch["tags_ok"]):
            logger.warning(
                "Language mismatch in enrich output, retrying once",
                extra={
                    "title": book_data.get("title"),
                    "target_lang": target_lang,
                    "mismatch": mismatch,
                },
            )
            retry_note = (
                f"Previous output language mismatch. Ensure summary and tags are strictly in {target_lang}."
            )
            enriched_data = await _run_enrich_once(book_data, target_lang, force_regenerate, retry_note=retry_note)
            mismatch = _language_mismatch_details(enriched_data, target_lang)

        if not mismatch["summary_ok"]:
            original_summary = str(book_data.get("summary") or "").strip()
            if original_summary and text_matches_target_language(original_summary, target_lang):
                enriched_data["summary"] = original_summary

        if not mismatch["tags_ok"]:
            original_tags = book_data.get("tags") if isinstance(book_data.get("tags"), list) else []
            if original_tags and tags_match_target_language(original_tags, target_lang):
                enriched_data["tags"] = sanitize_generated_tags(original_tags)

        if "confidence_scores" in enriched_data:
            scores = enriched_data["confidence_scores"]
            if enriched_data.get("pageCount") and scores.get("pageCount") == "low":
                logger.warning(
                    f"[AI AIKIDO] Low confidence pageCount estimated for '{book_data.get('title')}': {enriched_data['pageCount']}"
                )
            if enriched_data.get("translator") and scores.get("translator") == "low":
                logger.info(
                    f"[AI AIKIDO] Low confidence translator inferred for '{book_data.get('title')}': {enriched_data['translator']}"
                )

        final = {**book_data, **enriched_data}
        final["content_language_resolved"] = target_lang
        final["language_decision_reason"] = language_policy.get("reason")
        final["language_decision_confidence"] = language_policy.get("confidence")
        return final

    except Exception as e:
        logger.error(f"Enrichment failed: {e}")
        raise e


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
async def generate_tags_async(note_content: str) -> List[str]:
    try:
        model = get_model_for_tier(MODEL_TIER_FLASH)
        prompt = PROMPT_GENERATE_TAGS.format(note_content=note_content)
        result = await asyncio.wait_for(
            asyncio.to_thread(
                generate_text,
                model,
                prompt,
                "ai_generate_tags",
                MODEL_TIER_FLASH,
                None,
                None,
                None,
                30.0,
            ),
            timeout=30.0,
        )
        text = clean_json_response(result.text)

        parsed = json.loads(text)
        return sanitize_generated_tags(parsed)
    except Exception as e:
        logger.error(f"Tag gen failed: {e}")
        raise e


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
async def verify_cover_async(title: str, author: str, isbn: str = "") -> Optional[str]:
    try:
        model = get_model_for_tier(MODEL_TIER_FLASH)
        prompt = PROMPT_VERIFY_COVER.format(title=title, author=author, isbn=isbn or 'N/A')
        result = await asyncio.wait_for(
            asyncio.to_thread(
                generate_text,
                model,
                prompt,
                "ai_verify_cover",
                MODEL_TIER_FLASH,
                None,
                None,
                None,
                20.0,
            ),
            timeout=20.0,
        )
        url = result.text.strip()

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

        model = get_model_for_tier(MODEL_TIER_FLASH)
        text_block = "\n---\n".join(highlights)
        prompt = PROMPT_ANALYZE_HIGHLIGHTS.format(highlights_text=text_block)
        result = await asyncio.wait_for(
            asyncio.to_thread(
                generate_text,
                model,
                prompt,
                "ai_analyze_highlights",
                MODEL_TIER_FLASH,
                None,
                None,
                None,
                35.0,
            ),
            timeout=35.0,
        )
        return result.text.strip()
    except Exception as e:
        logger.error(f"Highlight analysis failed: {e}")
        raise e


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
async def search_resources_async(query: str, resource_type: str) -> List[Dict[str, Any]]:
    try:
        model = get_model_for_tier(MODEL_TIER_FLASH)
        prompt = PROMPT_SEARCH_RESOURCES.format(query=query, resource_type=resource_type)
        result = await asyncio.wait_for(
            asyncio.to_thread(
                generate_text,
                model,
                prompt,
                "ai_search_resources",
                MODEL_TIER_FLASH,
                None,
                None,
                None,
                30.0,
            ),
            timeout=30.0,
        )
        clean = clean_json_response(result.text)
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
        model = get_model_for_tier(MODEL_TIER_FLASH)
        prompt = PROMPT_EXTRACT_METADATA.format(text=text[:2000])
        result = await asyncio.wait_for(
            asyncio.to_thread(
                generate_text,
                model,
                prompt,
                "ai_extract_metadata",
                MODEL_TIER_FLASH,
                None,
                None,
                None,
                25.0,
            ),
            timeout=25.0,
        )
        clean = clean_json_response(result.text)
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
            enriched = await enrich_book_async(book)
            chunk = json.dumps(enriched, ensure_ascii=False) + "\n"
        except Exception as e:
            book["error"] = str(e)
            chunk = json.dumps(book, ensure_ascii=False) + "\n"

        chunk_bytes = len(chunk.encode("utf-8"))
        if total_bytes_sent + chunk_bytes > max_total_bytes:
            logger.warning(f"Stream volume limit reached ({max_total_bytes}). Closing stream.")
            yield json.dumps({"status": "limit_reached", "message": "Maximum stream volume exceeded"}) + "\n"
            break

        yield chunk
        total_bytes_sent += chunk_bytes

        await asyncio.sleep(0.5)
