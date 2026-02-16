from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import settings
from services.ai_service import enrich_book_async
from services.language_policy_service import (
    resolve_book_content_language,
    text_matches_target_language,
    tags_match_target_language,
)

logger = logging.getLogger(__name__)

_state: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "dry_run": False,
    "scope_uid": None,
    "processed": 0,
    "candidates": 0,
    "updated": 0,
    "failed": 0,
    "sample": [],
    "errors": [],
}
_task: Optional[asyncio.Task] = None


def _iso_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _reset_state(scope_uid: Optional[str], dry_run: bool) -> None:
    _state.update(
        {
            "running": True,
            "started_at": _iso_now(),
            "finished_at": None,
            "dry_run": bool(dry_run),
            "scope_uid": scope_uid,
            "processed": 0,
            "candidates": 0,
            "updated": 0,
            "failed": 0,
            "sample": [],
            "errors": [],
        }
    )


def get_language_backfill_status() -> Dict[str, Any]:
    status = dict(_state)
    status["sample"] = list(_state.get("sample", []))
    status["errors"] = list(_state.get("errors", []))
    return status


def _collect_candidate_payload(doc_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": str(doc_data.get("title") or ""),
        "author": str(doc_data.get("author") or ""),
        "publisher": str(doc_data.get("publisher") or ""),
        "isbn": str(doc_data.get("isbn") or ""),
        "summary": str(doc_data.get("generalNotes") or doc_data.get("summary") or ""),
        "tags": doc_data.get("tags") if isinstance(doc_data.get("tags"), list) else [],
        "content_language_mode": str(doc_data.get("contentLanguageMode") or "AUTO"),
        "source_language_hint": doc_data.get("sourceLanguageHint"),
    }


def _is_candidate_for_regen(payload: Dict[str, Any], target_lang: str) -> bool:
    summary = str(payload.get("summary") or "").strip()
    tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
    if not summary or not tags:
        return True
    return (not text_matches_target_language(summary, target_lang)) or (
        not tags_match_target_language(tags, target_lang)
    )


async def _run_backfill(
    scope_uid: Optional[str],
    dry_run: bool,
    batch_size: int,
    max_items: int,
) -> None:
    try:
        if not settings.FIREBASE_READY:
            raise RuntimeError("Firebase Admin SDK is not ready for language backfill")

        from firebase_admin import firestore

        db = firestore.client()
        if scope_uid:
            user_ids = [scope_uid]
        else:
            user_ids = [doc.id for doc in db.collection("users").stream()]

        since_pause = 0
        for uid in user_ids:
            if _state["processed"] >= max_items:
                break

            query = (
                db.collection("users")
                .document(uid)
                .collection("items")
                .where("type", "==", "BOOK")
            )

            for doc in query.stream():
                if _state["processed"] >= max_items:
                    break

                data = doc.to_dict() or {}
                payload = _collect_candidate_payload(data)
                if not payload["title"] or not payload["author"]:
                    continue

                _state["processed"] += 1
                policy = resolve_book_content_language(payload)
                target_lang = str(policy.get("resolved_lang") or "tr")
                if not _is_candidate_for_regen(payload, target_lang):
                    continue

                _state["candidates"] += 1
                if len(_state["sample"]) < 10:
                    _state["sample"].append(
                        {
                            "uid": uid,
                            "book_id": doc.id,
                            "title": payload["title"],
                            "target_lang": target_lang,
                            "reason": policy.get("reason"),
                        }
                    )

                if dry_run:
                    continue

                try:
                    enriched = await enrich_book_async(
                        {
                            **payload,
                            "force_regenerate": True,
                        }
                    )

                    patch: Dict[str, Any] = {
                        "contentLanguageMode": str(data.get("contentLanguageMode") or "AUTO").upper(),
                        "contentLanguageResolved": enriched.get("content_language_resolved") or target_lang,
                        "languageDecisionReason": enriched.get("language_decision_reason") or policy.get("reason"),
                        "languageDecisionConfidence": enriched.get("language_decision_confidence"),
                    }
                    if enriched.get("summary"):
                        patch["generalNotes"] = enriched.get("summary")
                    if isinstance(enriched.get("tags"), list):
                        patch["tags"] = enriched.get("tags")
                    source_hint = enriched.get("source_language_hint") or payload.get("source_language_hint")
                    if source_hint:
                        patch["sourceLanguageHint"] = source_hint

                    doc.reference.set(patch, merge=True)
                    _state["updated"] += 1
                except Exception as item_error:
                    _state["failed"] += 1
                    if len(_state["errors"]) < 20:
                        _state["errors"].append(
                            {
                                "uid": uid,
                                "book_id": doc.id,
                                "title": payload["title"],
                                "error": str(item_error),
                            }
                        )
                    logger.exception("Language backfill failed for book", extra={"uid": uid, "book_id": doc.id})

                # Keep pressure low to avoid throttling.
                since_pause += 1
                if since_pause >= batch_size:
                    await asyncio.sleep(0.35)
                    since_pause = 0
                else:
                    await asyncio.sleep(0.12)

            # Small pause between users in all-user runs.
            await asyncio.sleep(0.05)

    except Exception as e:
        _state["failed"] += 1
        if len(_state["errors"]) < 20:
            _state["errors"].append({"error": str(e)})
        logger.exception("Language backfill crashed")
    finally:
        _state["running"] = False
        _state["finished_at"] = _iso_now()


def start_language_backfill_async(
    scope_uid: Optional[str],
    dry_run: bool = False,
    batch_size: int = 25,
    max_items: int = 250,
) -> Dict[str, Any]:
    global _task

    if _task and not _task.done():
        return get_language_backfill_status()

    batch_size = max(1, min(int(batch_size), 100))
    max_items = max(1, min(int(max_items), 5000))
    _reset_state(scope_uid=scope_uid, dry_run=bool(dry_run))

    loop = asyncio.get_running_loop()
    _task = loop.create_task(_run_backfill(scope_uid, bool(dry_run), batch_size, max_items))
    return get_language_backfill_status()
