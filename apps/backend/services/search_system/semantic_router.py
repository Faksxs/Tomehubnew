from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Set


@dataclass
class RouterDecision:
    mode: str
    selected_buckets: List[str]
    reason: str
    retrieval_mode: str


class SemanticRouter:
    """
    Rule-based lightweight router.
    Decides which retrieval buckets should run for a query:
    - exact
    - lemma
    - semantic
    """

    DIRECT_PATTERNS = [
        r"\bhangi sayfa\b",
        r"\bkitab(?:i|ın|in) ad[ıi]\b",
        r"\bkim (dedi|s[öo]yledi)\b",
        r"\btam al[ıi]nt[ıi]\b",
        r"\"[^\"]+\"",
    ]

    CONCEPTUAL_HINTS = {
        "nedir",
        "neden",
        "nasil",
        "anlami",
        "kavram",
        "kavramsal",
        "etik",
        "ahlak",
        "felsefe",
        "adalet",
        "vicdan",
        "ozgurluk",
    }

    @staticmethod
    def buckets_for_mode(retrieval_mode: str) -> List[str]:
        mode = (retrieval_mode or "balanced").strip().lower()
        if mode == "fast_exact":
            return ["exact", "lemma"]
        if mode == "semantic_focus":
            return ["lemma", "semantic", "exact"]
        return ["exact", "lemma", "semantic"]

    def route(self, query: str, intent: str, default_mode: str = "balanced") -> RouterDecision:
        q = (query or "").strip().lower()
        # Tokenize by words (strip punctuation) so conceptual hints still match:
        # e.g. "nedir?" -> "nedir"
        tokens = [t for t in re.findall(r"[^\W_]+", q, flags=re.UNICODE) if t]
        token_set: Set[str] = set(tokens)

        # Intent-led fast path
        if intent in {"DIRECT", "CITATION_SEEKING", "FOLLOW_UP"}:
            retrieval_mode = "fast_exact"
            return RouterDecision(
                mode="rule_based",
                selected_buckets=self.buckets_for_mode(retrieval_mode),
                reason=f"intent={intent}",
                retrieval_mode=retrieval_mode,
            )

        # Pattern-led direct lookup style
        for pat in self.DIRECT_PATTERNS:
            if re.search(pat, q):
                retrieval_mode = "fast_exact"
                return RouterDecision(
                    mode="rule_based",
                    selected_buckets=self.buckets_for_mode(retrieval_mode),
                    reason=f"pattern:{pat}",
                    retrieval_mode=retrieval_mode,
                )

        # Conceptual question: semantic should be dominant but keep lexical safety
        if token_set.intersection(self.CONCEPTUAL_HINTS) and len(tokens) > 1:
            retrieval_mode = "semantic_focus"
            return RouterDecision(
                mode="rule_based",
                selected_buckets=self.buckets_for_mode(retrieval_mode),
                reason="conceptual_hint",
                retrieval_mode=retrieval_mode,
            )

        # Very short queries still need semantic coverage so Layer-2 can show
        # epistemic tail after direct matches.
        if len(tokens) <= 2:
            retrieval_mode = "balanced"
            return RouterDecision(
                mode="rule_based",
                selected_buckets=self.buckets_for_mode(retrieval_mode),
                reason="short_query",
                retrieval_mode=retrieval_mode,
            )

        # Default balanced path
        retrieval_mode = (default_mode or "balanced").strip().lower()
        return RouterDecision(
            mode="rule_based",
            selected_buckets=self.buckets_for_mode(retrieval_mode),
            reason="default_balanced",
            retrieval_mode=retrieval_mode,
        )


def to_strategy_labels(buckets: List[str]) -> Dict[str, bool]:
    selected = set(buckets or [])
    return {
        "run_exact": "exact" in selected,
        "run_lemma": "lemma" in selected,
        "run_semantic": "semantic" in selected,
    }
