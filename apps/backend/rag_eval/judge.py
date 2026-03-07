from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from config import settings
from services.llm_client import MODEL_TIER_FLASH, generate_text

from .models import GoldenCase, JudgeGrade


def _strip_code_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    return cleaned.strip()


def _coerce_score(value: Any) -> int:
    try:
        score = int(value)
    except Exception:
        return 0
    return max(0, min(5, score))


def _coerce_faithfulness(value: Any) -> str:
    text = str(value or "Unknown").strip().capitalize()
    if text not in {"High", "Medium", "Low", "Unknown"}:
        return "Unknown"
    return text


def _source_preview(sources: Iterable[Dict[str, Any]], limit: int = 4) -> str:
    rows: List[str] = []
    for index, source in enumerate(list(sources)[:limit], start=1):
        title = str(source.get("title") or "Unknown").strip()
        page = source.get("page_number") or "?"
        content = str(source.get("content") or "").strip()
        rows.append(f"{index}. {title} (page {page}): {content[:280]}")
    return "\n".join(rows) if rows else "No retrieved evidence."


def parse_judge_grade(text: str) -> JudgeGrade:
    try:
        payload = json.loads(_strip_code_fences(text))
    except Exception as exc:
        return JudgeGrade(
            score=0,
            reasoning=f"Judge output was not valid JSON: {exc}",
            faithfulness="Unknown",
            grounded=None,
        )
    return JudgeGrade(
        score=_coerce_score(payload.get("score")),
        reasoning=str(payload.get("reasoning") or "").strip() or "No reasoning provided.",
        faithfulness=_coerce_faithfulness(payload.get("faithfulness")),
        grounded=payload.get("grounded") if isinstance(payload.get("grounded"), bool) else None,
    )


class LLMJudge:
    def __init__(self, model: str | None = None):
        self.model = model or settings.LLM_MODEL_FLASH

    def evaluate(
        self,
        case: GoldenCase,
        answer: str,
        sources: List[Dict[str, Any]],
        meta: Dict[str, Any],
    ) -> JudgeGrade:
        prompt = f"""
You are evaluating a TomeHub RAG answer.

Question:
{case.question}

Reference answer:
{case.reference_answer or "N/A"}

Expected mode:
{case.expected_mode or "N/A"}

Key concepts:
{", ".join(case.key_concepts) or "N/A"}

Retrieved evidence:
{_source_preview(sources)}

RAG metadata:
{json.dumps(meta, ensure_ascii=False, sort_keys=True)}

Generated answer:
{answer or "EMPTY"}

Return JSON only:
{{
  "score": 0-5,
  "faithfulness": "High" | "Medium" | "Low" | "Unknown",
  "grounded": true | false,
  "reasoning": "Short explanation that separates retrieval failure from generation failure when possible"
}}
""".strip()
        result = generate_text(
            model=self.model,
            prompt=prompt,
            task="rag_eval_judge",
            model_tier=MODEL_TIER_FLASH,
            timeout_s=20.0,
            allow_pro_fallback=False,
        )
        return parse_judge_grade(result.text if result else "")
