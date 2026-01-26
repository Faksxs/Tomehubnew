"""
Rubric System - Quality Evaluation Criteria
============================================
Defines evaluation rubrics and scoring logic for the Judge AI.

The rubric provides structured, measurable criteria for answer quality,
enabling consistent evaluation and A/B testing of prompts.
"""

from typing import Dict, List


# =============================================================================
# DEFAULT RUBRIC
# =============================================================================

DEFAULT_RUBRIC: Dict[str, Dict] = {
    "source_accuracy": {
        "weight": 0.30,
        "description": "Are quotes verbatim? Are sources correctly cited?",
        "description_tr": "Alıntılar birebir mi? Kaynaklar doğru mu?",
        "failure_signals": ["misquote", "wrong_source", "fabricated_quote"],
        "hint": "Alıntıları kelimesi kelimesine kontrol et. Kaynak isimlerini doğrula."
    },
    "relevance": {
        "weight": 0.25,
        "description": "Does the answer directly address the question?",
        "description_tr": "Cevap soruyu doğrudan karşılıyor mu?",
        "failure_signals": ["off_topic", "tangential", "missing_core_concept"],
        "hint": "Sorunun ana kavramını (örn: 'vicdan') kaçırmış olabilirsin. Soruya odaklan."
    },
    "completeness": {
        "weight": 0.20,
        "description": "Are all aspects of the question covered?",
        "description_tr": "Sorunun tüm yönleri ele alındı mı?",
        "failure_signals": ["partial_answer", "missing_perspective"],
        "hint": "Sorunun birden fazla yönü var. Tüm perspektifleri ele al."
    },
    "ocr_correction": {
        "weight": 0.15,
        "description": "Were OCR artifacts properly corrected?",
        "description_tr": "OCR hataları düzeltildi mi?",
        "failure_signals": ["uncorrected_ocr", "garbled_text"],
        "hint": "Metindeki bozuk karakterleri düzelt (örn: 'dagas1' -> 'doğası')."
    },
    "format_compliance": {
        "weight": 0.10,
        "description": "Does output follow the requested structure?",
        "description_tr": "Çıktı istenen formata uyuyor mu?",
        "failure_signals": ["missing_headers", "wrong_section_count"],
        "hint": "İstenen başlıkları kullan: ## Doğrudan Tanımlar, ## Bağlamsal Analiz, ## Sonuç"
    }
}

# =============================================================================
# SPECIALIZED RUBRICS
# =============================================================================

DIRECT_RUBRIC: Dict[str, Dict] = {
    **DEFAULT_RUBRIC,
    "source_accuracy": {
        **DEFAULT_RUBRIC["source_accuracy"],
        "weight": 0.40,  # Higher weight for definitional questions
    },
    "relevance": {
        **DEFAULT_RUBRIC["relevance"],
        "weight": 0.25,
    },
    "completeness": {
        **DEFAULT_RUBRIC["completeness"],
        "weight": 0.15,
    },
}

SYNTHESIS_RUBRIC: Dict[str, Dict] = {
    **DEFAULT_RUBRIC,
    "source_accuracy": {
        **DEFAULT_RUBRIC["source_accuracy"],
        "weight": 0.20,  # Lower for synthesis
    },
    "relevance": {
        **DEFAULT_RUBRIC["relevance"],
        "weight": 0.30,  # Higher for synthesis
    },
    "completeness": {
        **DEFAULT_RUBRIC["completeness"],
        "weight": 0.30,  # Higher for synthesis
    },
}


def get_rubric_for_question(question: str, intent: str) -> Dict[str, Dict]:
    """
    Select appropriate rubric based on question intent.
    
    Args:
        question: The user's question
        intent: DIRECT | SYNTHESIS | COMPARATIVE
        
    Returns:
        Appropriate rubric dict
    """
    if intent == "DIRECT":
        return DIRECT_RUBRIC
    elif intent == "SYNTHESIS":
        return SYNTHESIS_RUBRIC
    else:
        return DEFAULT_RUBRIC


def get_hints_for_failures(failures: List[Dict]) -> List[str]:
    """
    Generate corrective hints based on identified failures.
    
    Args:
        failures: List of failure dicts from identify_failures()
        
    Returns:
        List of hint strings (max 3)
    """
    hints = []
    
    for failure in failures[:3]:  # Limit to 3 hints
        criterion = failure.get("criterion", "")
        
        # Look up hint from default rubric
        if criterion in DEFAULT_RUBRIC:
            hint = DEFAULT_RUBRIC[criterion].get("hint", f"Improve {criterion}")
            hints.append(hint)
    
    return hints

# Alias for backward compatibility/Judge AI usage
def generate_hints_from_failures(failures: List[Dict]) -> List[str]:
    return get_hints_for_failures(failures)



def format_rubric_as_table(rubric: Dict[str, Dict] = None, lang: str = "tr") -> str:
    """
    Format rubric as a markdown table for inclusion in Judge AI prompts.
    
    Args:
        rubric: Rubric definition. Uses DEFAULT_RUBRIC if None.
        lang: Language for descriptions ("en" or "tr")
        
    Returns:
        Formatted markdown table string.
    """
    if rubric is None:
        rubric = DEFAULT_RUBRIC
    
    desc_key = "description_tr" if lang == "tr" else "description"
    
    lines = ["| Kriter | Ağırlık | Açıklama |", "| --- | --- | --- |"]
    
    for name, config in rubric.items():
        weight_pct = int(config["weight"] * 100)
        desc = config.get(desc_key, config.get("description", ""))
        readable_name = name.replace("_", " ").title()
        lines.append(f"| {readable_name} | {weight_pct}% | {desc} |")
    
    return "\n".join(lines)


# =============================================================================
# SCORING FUNCTIONS
# =============================================================================

def calculate_overall_score(
    criterion_scores: Dict[str, float], 
    rubric: Dict[str, Dict] = None
) -> float:
    """
    Calculate weighted average of criterion scores.
    
    Args:
        criterion_scores: {"criterion_name": 0.0-1.0, ...}
        rubric: Rubric definition with weights. Uses DEFAULT_RUBRIC if None.
    
    Returns:
        Weighted average score (0.0 - 1.0)
    
    Example:
        >>> scores = {"source_accuracy": 0.9, "relevance": 0.8}
        >>> calculate_overall_score(scores)
        0.855  # Weighted by rubric
    """
    if rubric is None:
        rubric = DEFAULT_RUBRIC
    
    total_weight = 0.0
    weighted_sum = 0.0
    
    for name, config in rubric.items():
        weight = config["weight"]
        # Default to 0.5 if criterion not provided (neutral)
        score = criterion_scores.get(name, 0.5)
        
        # Clamp to valid range
        score = max(0.0, min(1.0, score))
        
        weighted_sum += weight * score
        total_weight += weight
    
    if total_weight == 0:
        return 0.5
    
    return weighted_sum / total_weight


def get_rubric_description(rubric: Dict[str, Dict] = None, lang: str = "tr") -> str:
    """
    Get human-readable rubric description for prompts.
    
    Args:
        rubric: Rubric definition. Uses DEFAULT_RUBRIC if None.
        lang: Language for descriptions ("en" or "tr")
    
    Returns:
        Formatted string with criterion names, weights, and descriptions.
    """
    if rubric is None:
        rubric = DEFAULT_RUBRIC
    
    lines = []
    desc_key = "description_tr" if lang == "tr" else "description"
    
    for name, config in rubric.items():
        weight_pct = int(config["weight"] * 100)
        desc = config.get(desc_key, config["description"])
        readable_name = name.replace("_", " ").title()
        lines.append(f"- {readable_name} ({weight_pct}%): {desc}")
    
    return "\n".join(lines)


def get_rubric_summary(rubric: Dict[str, Dict] = None) -> str:
    """
    Get brief rubric summary for logging/debugging.
    
    Returns:
        Single-line summary of criteria and weights.
    """
    if rubric is None:
        rubric = DEFAULT_RUBRIC
    
    parts = []
    for name, config in rubric.items():
        weight_pct = int(config["weight"] * 100)
        parts.append(f"{name}:{weight_pct}%")
    
    return " | ".join(parts)


def identify_failures(
    criterion_scores: Dict[str, float],
    threshold: float = 0.5,
    rubric: Dict[str, Dict] = None
) -> List[Dict[str, str]]:
    """
    Identify which criteria failed below threshold.
    
    Args:
        criterion_scores: {"criterion_name": 0.0-1.0, ...}
        threshold: Score below which a criterion is considered failed
        rubric: Rubric definition for failure signals
    
    Returns:
        List of dicts with criterion name, score, and possible failure signals.
    """
    if rubric is None:
        rubric = DEFAULT_RUBRIC
    
    failures = []
    
    for name, config in rubric.items():
        score = criterion_scores.get(name, 0.5)
        if score < threshold:
            failures.append({
                "criterion": name,
                "score": score,
                "weight": config["weight"],
                "possible_issues": config.get("failure_signals", [])
            })
    
    return failures


# =============================================================================
# THRESHOLDS
# =============================================================================

# Quality thresholds for Judge AI decisions
THRESHOLDS = {
    "pass": 0.65,           # >= this score: answer is good
    "regenerate": 0.50,     # >= this but < pass: try again with hints
    "decline": 0.50         # < this: decline to answer
}


# Adaptive Threshold Logic (Phase 1, Enhancement 5)
def get_adaptive_threshold(intent: str, chunk_quality: float, criterion_scores: Dict[str, float]) -> Dict[str, float]:
    """
    Calculate adaptive thresholds based on question type and context quality.
    """
    import os
    base_pass = float(os.getenv('DUAL_AI_BASE_THRESHOLD', '0.65'))
    base_regen = float(os.getenv('DUAL_AI_REGENERATE_THRESHOLD', '0.50'))
    
    # Adjustment 1: Per-question-type (Intent)
    if intent == "DIRECT":
        # For definitional questions, require higher quality
        pass_threshold = base_pass + 0.05
    elif intent == "SYNTHESIS":
        # For synthesis, allow more flexibility
        pass_threshold = base_pass - 0.05
    else:
        pass_threshold = base_pass
    
    # Adjustment 2: Confidence-based (chunk quality)
    if chunk_quality < 3.0:  # Low-quality source data
        pass_threshold -= 0.10  # Lower bar when sources are weak
    elif chunk_quality >= 5.0:  # High-quality sources
        pass_threshold += 0.05  # Raise bar when sources are strong
    
    # Adjustment 3: Failure pattern count
    failure_count = sum(1 for score in criterion_scores.values() if score < 0.5)
    if failure_count >= 3:
        # Multiple failures -> raise bar for regeneration
        regen_threshold = base_regen + 0.10
    else:
        regen_threshold = base_regen
    
    # Clamp to reasonable ranges
    pass_threshold = max(0.55, min(0.75, pass_threshold))
    regen_threshold = min(pass_threshold - 0.1, max(0.40, regen_threshold))
    
    return {
        "pass": pass_threshold,
        "regenerate": regen_threshold
    }

def get_verdict(
    overall_score: float, 
    intent: str = "SYNTHESIS", 
    chunk_quality: float = 4.0, 
    criterion_scores: Dict[str, float] = None
) -> str:
    """
    Determine verdict based on overall score, potentially using adaptive thresholds.
    """
    if criterion_scores is None:
        criterion_scores = {}
        
    thresholds = get_adaptive_threshold(intent, chunk_quality, criterion_scores)
    
    if overall_score >= thresholds["pass"]:
        return "PASS"
    elif overall_score >= thresholds["regenerate"]:
        return "REGENERATE"
    else:
        return "DECLINE"


# =============================================================================
# MODULE TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Rubric System - Test")
    print("=" * 60)
    
    # Test 1: Basic scoring
    test_scores = {
        "source_accuracy": 0.9,
        "relevance": 0.85,
        "completeness": 0.7,
        "ocr_correction": 0.95,
        "format_compliance": 0.8
    }
    
    overall = calculate_overall_score(test_scores)
    verdict = get_verdict(overall)
    
    print(f"\nTest Scores: {test_scores}")
    print(f"Overall Score: {overall:.3f}")
    print(f"Verdict: {verdict}")
    
    # Test 2: Low score with failures
    low_scores = {
        "source_accuracy": 0.3,
        "relevance": 0.4,
        "completeness": 0.5,
        "ocr_correction": 0.6,
        "format_compliance": 0.7
    }
    
    overall_low = calculate_overall_score(low_scores)
    failures = identify_failures(low_scores)
    
    print(f"\nLow Scores: {low_scores}")
    print(f"Overall Score: {overall_low:.3f}")
    print(f"Failures: {failures}")
    
    # Test 3: Rubric description
    print(f"\nRubric Description (TR):")
    print(get_rubric_description(lang="tr"))
    
    print("\n" + "=" * 60)
