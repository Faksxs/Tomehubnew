# -*- coding: utf-8 -*-
from typing import List, Dict, Tuple, Any
from services.epistemic_service import extract_core_concepts


def _has_primary_religious_evidence(chunks: List[Dict[str, Any]]) -> bool:
    for chunk in chunks[:5]:
        source_type = str(chunk.get("source_type") or "").strip().upper()
        religious_kind = str(chunk.get("religious_source_kind") or "").strip().upper()
        if source_type == "ISLAMIC_EXTERNAL" and religious_kind in {"QURAN", "HADITH"}:
            return True
    return False


def classify_network_status(
    query: str, 
    chunks: List[Dict], 
    min_confidence: float = 3.0
) -> Dict[str, Any]:
    """
    Determines if the query is covered by the user's library (IN-NETWORK)
    or requires external knowledge (OUT-OF-NETWORK).
    
    Logic:
    1. Keyword Coverage: Do the retrieved chunks contain the query keywords?
    2. Epistemic Density: Is there enough 'Level A/B' content?
    3. Similarity Scores: Are the vector scores high enough?
    """
    
    if not chunks:
        return {
            "status": "OUT_OF_NETWORK",
            "confidence": 0.0,
            "reason": "No content found"
        }
        
    # 1. Analyze Confidence Scores (from Epistemic Service)
    # answerability_score is 0-7
    top_chunks = chunks[:5]
    avg_score = sum(c.get('answerability_score', 0) for c in top_chunks) / max(1, len(top_chunks))
    
    # 2. Analyze Keyword Coverage
    keywords = extract_core_concepts(query)
    covered_keywords = set()
    
    combined_text = " ".join([str(c.get('content_chunk', '')).lower() for c in top_chunks])
    
    for kw in keywords:
        if kw.lower() in combined_text:
            covered_keywords.add(kw)
            
    coverage_ratio = len(covered_keywords) / max(1, len(keywords))
    
    # 3. Determine Status
    status = "HYBRID"
    confidence = avg_score / 7.0 # Normalize to 0-1
    has_primary_religious_evidence = _has_primary_religious_evidence(top_chunks)
    
    # Criteria for IN_NETWORK:
    # - High epistemic score (>4.0) indicating good definition/context
    # - OR High keyword coverage (>80%) with moderate/low score (e.g. philosophical comparisons)
    
    if has_primary_religious_evidence and coverage_ratio >= 0.5:
        status = "IN_NETWORK"
    elif avg_score >= 5.0 and coverage_ratio >= 0.5:
        status = "IN_NETWORK"
    elif avg_score >= 3.5 and coverage_ratio >= 0.7:
        status = "IN_NETWORK"
    elif avg_score >= 1.0 and coverage_ratio >= 0.8:
        # Felsefi/Karşılaştırmalı notlar genelde net tanım içermez ama keyword kapsayıcılığı yüksektir.
        status = "IN_NETWORK"
    elif avg_score < 2.0 and coverage_ratio < 0.8:
        status = "OUT_OF_NETWORK"
        
    return {
        "status": status,
        "confidence": confidence,
        "metrics": {
            "avg_epistemic_score": avg_score,
            "coverage_ratio": coverage_ratio,
            "missing_keywords": list(set(keywords) - covered_keywords),
            "has_primary_religious_evidence": has_primary_religious_evidence,
        },
        "reason": f"Score {avg_score:.1f}, Coverage {int(coverage_ratio*100)}%"
    }
