import json
import re
from typing import List, Tuple

from utils.text_utils import normalize_text


def _parse_list_string(value: str) -> List[str]:
    if not value:
        return []
    text = value.strip()
    if not text:
        return []

    # Try JSON array first
    if text.startswith("[") and text.endswith("]"):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except Exception:
            pass

    # Fallback: comma/semicolon split
    text = text.replace("\n", ",")
    parts = re.split(r"[;,]", text)
    return [p.strip() for p in parts if p.strip()]


def normalize_label(label: str) -> str:
    if not label:
        return ""
    return normalize_text(label).lower()


def prepare_labels(value: str) -> List[Tuple[str, str]]:
    """
    Returns list of (raw_label, normalized_label) tuples, de-duplicated by normalized.
    """
    labels = _parse_list_string(value)
    prepared = []
    seen = set()
    for label in labels:
        raw = label.strip()
        if not raw:
            continue
        norm = normalize_label(raw)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        prepared.append((raw[:255], norm[:255]))
    return prepared
