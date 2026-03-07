from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .models import GoldenCase


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_list_item(raw: Dict[str, Any]) -> GoldenCase:
    case_id = str(raw.get("id") or raw.get("case_id") or "").strip()
    question = str(raw.get("question") or raw.get("query") or "").strip()
    if not case_id or not question:
        raise ValueError(f"Invalid golden case payload: {raw}")
    metadata = {
        key: value
        for key, value in raw.items()
        if key
        not in {
            "id",
            "case_id",
            "question",
            "query",
            "reference_answer",
            "expected_mode",
            "key_concepts",
            "must_quote",
            "must_synthesize",
            "forbidden",
        }
    }
    return GoldenCase(
        case_id=case_id,
        question=question,
        reference_answer=str(raw.get("reference_answer") or "").strip(),
        expected_mode=str(raw.get("expected_mode") or "").strip() or None,
        key_concepts=_as_list(raw.get("key_concepts")),
        must_quote=_as_list(raw.get("must_quote")),
        must_synthesize=_as_list(raw.get("must_synthesize")),
        forbidden=_as_list(raw.get("forbidden")),
        metadata=metadata,
    )


def _normalize_mapping_items(raw: Dict[str, Any]) -> Iterable[GoldenCase]:
    for case_id, payload in raw.items():
        if not isinstance(payload, dict):
            raise ValueError(f"Golden case '{case_id}' must be an object.")
        normalized = dict(payload)
        normalized["case_id"] = case_id
        yield _normalize_list_item(normalized)


def load_golden_cases(dataset_path: str | Path) -> List[GoldenCase]:
    path = Path(dataset_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [_normalize_list_item(item) for item in payload]
    if isinstance(payload, dict):
        return list(_normalize_mapping_items(payload))
    raise ValueError(f"Unsupported dataset format in {path}")
