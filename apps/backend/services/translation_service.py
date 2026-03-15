from __future__ import annotations

"""Translation service for TomeHub."""

import asyncio
import json
import logging
import re
from typing import Dict, Optional

from config import settings
from infrastructure.db_manager import DatabaseManager
from services.llm_client import (
    MODEL_TIER_FLASH,
    PROVIDER_QWEN,
    generate_text,
)

logger = logging.getLogger("tomehub_api")


TRANSLATION_SYSTEM_PROMPT = """You are an expert translator who faithfully translates texts
from Turkish into English and Dutch. You preserve the original tone, style, and terminology
of the source text - whether it is philosophical, literary, historical, sociological,
scientific, or any other genre.

RULES:
- Preserve domain-specific terms and proper nouns
- Match the register of the original (formal, literary, colloquial, etc.)
- Do NOT simplify, summarize, or paraphrase - translate faithfully
- If a term has an established translation in the target language, use it
- Maintain the original sentence structure where it serves clarity
"""

TRANSLATION_USER_PROMPT = """Translate the following Turkish text into BOTH English and Dutch.

CONTEXT (use this to guide your translation choices):
- Book Title: "{book_title}"
- Author: {book_author}
- Categories: {tags}

SOURCE TEXT:
{source_text}

Return ONLY valid JSON in this exact format:
{{"en": "English translation here", "nl": "Dutch translation here"}}"""
def _get_cached_translation(content_id: int) -> Optional[Dict[str, Any]]:
    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT LANG_EN, LANG_NL, ETYMOLOGY_JSON FROM TOMEHUB_TRANSLATIONS WHERE CONTENT_ID = :cid",
                {"cid": content_id},
            )
            row = cur.fetchone()
            if not row:
                return None

            en_text = row[0]
            nl_text = row[1]
            etymology_raw = row[2]

            if hasattr(en_text, "read"):
                en_text = en_text.read()
            if hasattr(nl_text, "read"):
                nl_text = nl_text.read()
            if hasattr(etymology_raw, "read"):
                etymology_raw = etymology_raw.read()

            etymology = None
            if etymology_raw:
                try:
                    etymology = json.loads(etymology_raw)
                except Exception:
                    etymology = None

            return {"en": en_text or "", "nl": nl_text or "", "etymology": etymology}


def _save_translation(content_id: int, firebase_uid: str, en: str, nl: str) -> None:
    with DatabaseManager.get_write_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                MERGE INTO TOMEHUB_TRANSLATIONS t
                USING (SELECT :cid AS CID_VAL, :fuid AS UID_VAL, :en AS EN_VAL, :nl AS NL_VAL FROM DUAL) s
                ON (t.CONTENT_ID = s.CID_VAL)
                WHEN NOT MATCHED THEN
                    INSERT (CONTENT_ID, FIREBASE_UID, LANG_EN, LANG_NL)
                    VALUES (s.CID_VAL, s.UID_VAL, s.EN_VAL, s.NL_VAL)
                """,
                {"cid": content_id, "fuid": firebase_uid, "en": en, "nl": nl},
            )
            conn.commit()
    logger.info("Translation saved for content_id=%s", content_id)


def check_translation_exists(content_ids: list[int]) -> dict[int, bool]:
    if not content_ids:
        return {}

    with DatabaseManager.get_read_connection() as conn:
        with conn.cursor() as cur:
            placeholders = ",".join(f":id{i}" for i in range(len(content_ids)))
            binds = {f"id{i}": cid for i, cid in enumerate(content_ids)}
            cur.execute(
                f"SELECT CONTENT_ID FROM TOMEHUB_TRANSLATIONS WHERE CONTENT_ID IN ({placeholders})",
                binds,
            )
            existing = {row[0] for row in cur.fetchall()}

    return {cid: (cid in existing) for cid in content_ids}


async def translate_chunk(
    content_id: int,
    firebase_uid: str,
    source_text: str,
    book_title: str = "",
    book_author: str = "",
    tags: str = "",
) -> Dict[str, Any]:
    cached = _get_cached_translation(content_id)
    if cached:
        logger.debug("Translation cache hit for content_id=%s", content_id)
        return {
            "en": cached["en"],
            "nl": cached["nl"],
            "etymology": cached.get("etymology"),
            "cached": True,
        }

    prompt = TRANSLATION_SYSTEM_PROMPT + "\n\n" + TRANSLATION_USER_PROMPT.format(
        book_title=book_title or "Unknown",
        book_author=book_author or "Unknown",
        tags=tags or "General",
        source_text=source_text,
    )

    model = settings.LLM_EXPLORER_PRIMARY_MODEL.replace("-thinking", "-instruct")

    result = await asyncio.wait_for(
        asyncio.to_thread(
            generate_text,
            model,
            prompt,
            "translate_chunk",
            MODEL_TIER_FLASH,
            0.2,
            1200,
            "application/json",
            30.0,
            False,
            None,
            PROVIDER_QWEN,
        ),
        timeout=35.0,
    )

    raw = result.text.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*?\})", raw, re.DOTALL)
        if match:
            parsed = json.loads(match.group(1))
        else:
            logger.error("Translation LLM returned invalid JSON: %s", raw[:300])
            raise ValueError("Translation failed: invalid LLM response")

    en_text = parsed.get("en", "")
    nl_text = parsed.get("nl", "")
    if not en_text and not nl_text:
        raise ValueError("Translation failed: empty result from LLM")

    _save_translation(content_id, firebase_uid, en_text, nl_text)
    return {"en": en_text, "nl": nl_text, "etymology": None, "cached": False}
