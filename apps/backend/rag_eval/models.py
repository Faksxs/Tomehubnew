from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GoldenCase:
    case_id: str
    question: str
    reference_answer: str = ""
    expected_mode: Optional[str] = None
    key_concepts: List[str] = field(default_factory=list)
    must_quote: List[str] = field(default_factory=list)
    must_synthesize: List[str] = field(default_factory=list)
    forbidden: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JudgeGrade:
    score: int
    reasoning: str
    faithfulness: str = "Unknown"
    grounded: Optional[bool] = None


@dataclass
class EvalCaseResult:
    case_id: str
    question: str
    answer: str
    actual_mode: Optional[str]
    source_count: int
    source_titles: List[str]
    duration_sec: float
    score: int
    faithfulness: str
    passed: bool
    classification: str
    evidence_gaps: List[str]
    rule_failures: List[str]
    reasoning: str
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalSummary:
    total_cases: int
    passed_cases: int
    pass_rate: float
    average_score: float
    average_latency_sec: float
    classifications: Dict[str, int]
    faithfulness_counts: Dict[str, int]
