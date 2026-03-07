from __future__ import annotations

from typing import Optional


def resolve_result_mix_policy(
    requested_policy: Optional[str],
    *,
    fusion_mode: str,
    default_policy: str,
) -> Optional[str]:
    if requested_policy is not None:
        normalized = str(requested_policy).strip().lower()
        if normalized in {"", "none", "off"}:
            return None
        return normalized

    normalized_default = str(default_policy or "auto").strip().lower()
    if normalized_default == "auto":
        return None if str(fusion_mode or "").strip().lower() == "rrf" else "lexical_then_semantic_tail"
    if normalized_default in {"", "none", "off"}:
        return None
    return normalized_default
