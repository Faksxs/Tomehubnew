# -*- coding: utf-8 -*-
"""
Query planning primitives for Layer-3 orchestration.

This module keeps intent routing and compare-trigger decisions explicit so
retrieval logic can remain deterministic and measurable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
import re

from utils.text_utils import normalize_text

PLAN_ANALYTIC = "ANALYTIC"
PLAN_COMPARE = "COMPARE"
PLAN_SYNTHESIS = "SYNTHESIS"
PLAN_DIRECT = "DIRECT"
PLAN_EXPLORER = "EXPLORER"


@dataclass
class QueryPlan:
    plan_type: str
    intent: str
    compare_requested: bool = False
    notes_vs_book_compare_requested: bool = False
    target_book_ids: List[str] = field(default_factory=list)
    compare_mode_effective: str = "EXPLICIT_ONLY"
    scope_override: Optional[str] = None
    degrade_reason: str = ""


def normalize_compare_mode(compare_mode: Optional[str]) -> str:
    mode = str(compare_mode or "EXPLICIT_ONLY").strip().upper() or "EXPLICIT_ONLY"
    if mode not in {"EXPLICIT_ONLY", "AUTO"}:
        return "EXPLICIT_ONLY"
    return mode


def looks_explicit_compare_query(question: str) -> bool:
    q = normalize_text(question).lower()
    patterns = (
        r"\bkarsilast",
        r"\bkiyasla",
        r"\bdiger kitap",
        r"\bdiger yazar",
        r"\barasinda",
        r"\bfarki",
        r"\bnasil degis",
        r"\bnasil farkl",
    )
    return any(re.search(pat, q) for pat in patterns)


def looks_user_notes_compare_query(question: str) -> bool:
    q = normalize_text(question).lower()
    note_patterns = (
        r"\bnotlarim",
        r"\bnotlarimdaki",
        r"\bnotlarimda",
        r"\bnotlar",
        r"\bhighlight",
        r"\binsight",
        r"\bcomment",
        r"\byorum",
    )
    return any(re.search(pat, q) for pat in note_patterns)


def build_query_plan(
    *,
    question: str,
    intent: str,
    is_analytic: bool,
    compare_mode: Optional[str],
    target_book_ids: List[str],
    context_book_id: Optional[str],
    auto_resolved_compare_book_ids: List[str],
) -> QueryPlan:
    mode = normalize_compare_mode(compare_mode)
    compare_query_explicit = looks_explicit_compare_query(question)
    compare_notes_requested = looks_user_notes_compare_query(question)

    requested_targets = [str(b or "").strip() for b in (target_book_ids or []) if str(b or "").strip()]
    if requested_targets:
        effective_targets = requested_targets
    else:
        effective_targets = [str(b or "").strip() for b in (auto_resolved_compare_book_ids or []) if str(b or "").strip()]

    has_compare_targets = len(effective_targets) >= 2
    has_notes_anchor = bool(str(context_book_id or "").strip())

    if is_analytic:
        return QueryPlan(plan_type=PLAN_ANALYTIC, intent=intent)

    compare_requested = False
    notes_vs_book_compare_requested = False
    degrade_reason = ""

    if has_compare_targets:
        if mode == "AUTO":
            compare_requested = intent == "COMPARATIVE"
        else:
            compare_requested = compare_query_explicit or intent == "COMPARATIVE"

    if (
        not compare_requested
        and has_notes_anchor
        and compare_query_explicit
        and compare_notes_requested
    ):
        if mode == "AUTO":
            notes_vs_book_compare_requested = intent == "COMPARATIVE"
        else:
            notes_vs_book_compare_requested = True

    if has_compare_targets and not compare_requested:
        if mode == "AUTO" and intent != "COMPARATIVE":
            degrade_reason = "auto_mode_non_comparative_intent"
        elif mode == "EXPLICIT_ONLY" and not (compare_query_explicit or intent == "COMPARATIVE"):
            degrade_reason = "explicit_compare_not_detected"
    elif effective_targets and len(effective_targets) < 2:
        degrade_reason = "insufficient_target_books"
    elif has_notes_anchor and compare_notes_requested and not compare_query_explicit:
        degrade_reason = "notes_compare_missing_explicit_compare_signal"

    if compare_requested or notes_vs_book_compare_requested:
        return QueryPlan(
            plan_type=PLAN_COMPARE,
            intent=intent,
            compare_requested=compare_requested,
            notes_vs_book_compare_requested=notes_vs_book_compare_requested,
            target_book_ids=effective_targets,
            compare_mode_effective=mode,
            scope_override="GLOBAL",
            degrade_reason=degrade_reason,
        )

    if intent in {"SYNTHESIS", "COMPARATIVE", "NARRATIVE", "SOCIETAL"}:
        plan_type = PLAN_SYNTHESIS
    elif intent in {"DIRECT", "FOLLOW_UP"}:
        plan_type = PLAN_DIRECT
    else:
        plan_type = PLAN_EXPLORER

    return QueryPlan(
        plan_type=plan_type,
        intent=intent,
        compare_requested=False,
        notes_vs_book_compare_requested=False,
        target_book_ids=effective_targets,
        compare_mode_effective=mode,
        degrade_reason=degrade_reason,
    )

