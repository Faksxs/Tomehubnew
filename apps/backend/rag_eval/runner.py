from __future__ import annotations

import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Sequence, Tuple
from unidecode import unidecode

from .models import EvalCaseResult, EvalSummary, GoldenCase, JudgeGrade


AnswerFn = Callable[[GoldenCase, str], Tuple[str, List[Dict[str, Any]], Dict[str, Any]]]


def _default_answer_fn(case: GoldenCase, firebase_uid: str) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    from services.search_service import generate_answer

    response = generate_answer(case.question, firebase_uid)
    if isinstance(response, tuple) and len(response) == 3:
        answer, sources, meta = response
        return answer or "", sources or [], meta or {}
    if isinstance(response, tuple) and len(response) == 2:
        answer, sources = response
        return answer or "", sources or [], {}
    raise RuntimeError("generate_answer returned an unexpected payload.")


def _normalize_text(text: str) -> str:
    normalized = unidecode(str(text or "")).lower()
    return " ".join(normalized.split())


def infer_answer_mode(answer: str) -> str | None:
    normalized = _normalize_text(answer)
    if "## karsit gorusler" in normalized and "## baglamsal kanitlar" in normalized:
        return "HYBRID"
    if "## dogrudan tanimlar" in normalized and "## baglamsal analiz" in normalized:
        return "QUOTE"
    if "## sonuc" in normalized:
        return "SYNTHESIS"
    return None


def evaluate_case_rules(case: GoldenCase, answer: str) -> Tuple[List[str], str | None]:
    normalized_answer = _normalize_text(answer)
    actual_mode = infer_answer_mode(answer)
    failures: List[str] = []

    if case.expected_mode and actual_mode and actual_mode != case.expected_mode:
        failures.append(f"mode_mismatch:{actual_mode}")
    elif case.expected_mode and not actual_mode:
        failures.append("mode_unknown")

    for phrase in case.must_quote:
        if _normalize_text(phrase) not in normalized_answer:
            failures.append(f"missing_required_phrase:{phrase}")

    for phrase in case.must_synthesize:
        if _normalize_text(phrase) not in normalized_answer:
            failures.append(f"missing_synthesis_signal:{phrase}")

    for phrase in case.forbidden:
        if _normalize_text(phrase) in normalized_answer:
            failures.append(f"forbidden_phrase_present:{phrase}")

    return failures, actual_mode


def classify_case_result(
    answer: str,
    sources: Sequence[Dict[str, Any]],
    meta: Dict[str, Any],
    grade: JudgeGrade,
    rule_failures: Sequence[str],
    *,
    pass_score: int = 4,
) -> Tuple[str, List[str], bool]:
    evidence_gaps: List[str] = []
    if not sources:
        evidence_gaps.append("no_sources")
    if meta.get("status") in {"failed", "error"}:
        evidence_gaps.append(f"pipeline_status:{meta.get('status')}")
    if grade.score < pass_score:
        evidence_gaps.append("low_score")
    if grade.faithfulness == "Low":
        evidence_gaps.append("low_faithfulness")
    if not (answer or "").strip():
        evidence_gaps.append("empty_answer")
    evidence_gaps.extend(rule_failures)

    retrieval_failure = (
        not sources
        or meta.get("status") == "failed"
        or (
            int(meta.get("vector_candidates_count", 0) or 0) == 0
            and int(meta.get("source_diversity_count", 0) or 0) == 0
        )
    )
    generation_failure = bool(sources) and (
        grade.score < pass_score or grade.faithfulness == "Low" or bool(rule_failures)
    )

    if not evidence_gaps:
        return "pass", [], True
    if retrieval_failure and generation_failure:
        return "mixed", evidence_gaps, False
    if retrieval_failure:
        return "retrieval", evidence_gaps, False
    if generation_failure:
        return "generation", evidence_gaps, False
    return "unknown", evidence_gaps, False


def run_eval_suite(
    cases: Iterable[GoldenCase],
    firebase_uid: str,
    judge: Any,
    *,
    answer_fn: AnswerFn | None = None,
    pass_score: int = 4,
) -> Tuple[List[EvalCaseResult], EvalSummary]:
    caller = answer_fn or _default_answer_fn
    results: List[EvalCaseResult] = []

    for case in cases:
        started_at = time.perf_counter()
        answer, sources, meta = caller(case, firebase_uid)
        duration_sec = time.perf_counter() - started_at
        grade = judge.evaluate(case, answer, sources, meta)
        rule_failures, actual_mode = evaluate_case_rules(case, answer)
        classification, evidence_gaps, passed = classify_case_result(
            answer,
            sources,
            meta,
            grade,
            rule_failures,
            pass_score=pass_score,
        )
        results.append(
            EvalCaseResult(
                case_id=case.case_id,
                question=case.question,
                answer=answer,
                actual_mode=actual_mode,
                source_count=len(sources),
                source_titles=sorted(
                    {
                        str(source.get("title") or "").strip()
                        for source in sources
                        if str(source.get("title") or "").strip()
                    }
                ),
                duration_sec=duration_sec,
                score=grade.score,
                faithfulness=grade.faithfulness,
                passed=passed,
                classification=classification,
                evidence_gaps=evidence_gaps,
                rule_failures=rule_failures,
                reasoning=grade.reasoning,
                meta=meta,
            )
        )

    classification_counts = Counter(item.classification for item in results)
    faithfulness_counts = Counter(item.faithfulness for item in results)
    total_cases = len(results)
    passed_cases = sum(1 for item in results if item.passed)
    average_score = (
        sum(item.score for item in results) / total_cases if total_cases else 0.0
    )
    average_latency = (
        sum(item.duration_sec for item in results) / total_cases if total_cases else 0.0
    )
    summary = EvalSummary(
        total_cases=total_cases,
        passed_cases=passed_cases,
        pass_rate=(passed_cases / total_cases) if total_cases else 0.0,
        average_score=average_score,
        average_latency_sec=average_latency,
        classifications=dict(classification_counts),
        faithfulness_counts=dict(faithfulness_counts),
    )
    return results, summary


def render_markdown_report(
    results: Sequence[EvalCaseResult],
    summary: EvalSummary,
    *,
    dataset_name: str,
    generated_at: datetime | None = None,
) -> str:
    timestamp = (generated_at or datetime.now(UTC)).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# TomeHub RAG Eval Report",
        "",
        f"- Dataset: `{dataset_name}`",
        f"- Generated: `{timestamp}`",
        f"- Cases: `{summary.total_cases}`",
        f"- Passed: `{summary.passed_cases}`",
        f"- Pass rate: `{summary.pass_rate:.1%}`",
        f"- Average score: `{summary.average_score:.2f}/5`",
        f"- Average latency: `{summary.average_latency_sec:.2f}s`",
        "",
        "## Classification Counts",
        "",
    ]
    for key, value in sorted(summary.classifications.items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Case Results", "", "| ID | Score | Faithfulness | Mode | Class | Sources | Notes |", "|---|---:|---|---|---|---:|---|"])
    for item in results:
        notes = ", ".join(item.evidence_gaps) if item.evidence_gaps else "pass"
        notes = notes.replace("|", "/")
        lines.append(
            f"| {item.case_id} | {item.score} | {item.faithfulness} | {item.actual_mode or '-'} | {item.classification} | {item.source_count} | {notes} |"
        )
    return "\n".join(lines) + "\n"


def render_json_report(results: Sequence[EvalCaseResult], summary: EvalSummary) -> str:
    payload = {
        "summary": summary.__dict__,
        "results": [item.__dict__ for item in results],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def write_reports(
    output_dir: str | Path,
    dataset_name: str,
    results: Sequence[EvalCaseResult],
    summary: EvalSummary,
) -> Tuple[Path, Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    markdown_path = out_dir / f"rag_eval_{dataset_name}_{stamp}.md"
    json_path = out_dir / f"rag_eval_{dataset_name}_{stamp}.json"
    markdown_path.write_text(
        render_markdown_report(results, summary, dataset_name=dataset_name),
        encoding="utf-8",
    )
    json_path.write_text(render_json_report(results, summary), encoding="utf-8")
    return markdown_path, json_path
