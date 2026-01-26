# -*- coding: utf-8 -*-
import os
import json
import re
import logging
import asyncio
from typing import Dict, List, Any, Tuple
import google.generativeai as genai
from services.rubric import (
    DEFAULT_RUBRIC, 
    get_rubric_for_question, 
    format_rubric_as_table,
    calculate_overall_score,
    identify_failures,
    get_verdict,
    generate_hints_from_failures
)
from services.embedding_service import get_embedding
from utils.spell_checker import get_spell_checker
import numpy as np

logger = logging.getLogger(__name__)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if not v1 or not v2:
        return 0.0
    
    vec1 = np.array(v1)
    vec2 = np.array(v2)
    
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
        
    return float(np.dot(vec1, vec2) / (norm1 * norm2))

def extract_citations_from_answer(answer: str) -> List[Dict[str, str]]:
    """
    Extract citations from answer text.
    Expected format: "...text..." [Kaynak: Title]
    or markdown links: [Title](source)
    """
    citations = []
    
    # Pattern 1: [Kaynak: Title]
    # Capture text before it optionally? No, that's hard. 
    # Just capture source names for now to verify existence.
    # For text verification, we'll split by sentences or look for quotes.
    
    # Simple regex for source tags
    source_matches = re.finditer(r'\[Kaynak:\s*(.*?)\]', answer)
    for match in source_matches:
        source_name = match.group(1).strip()
        # Try to find the sentence/quote preceding this source
        # Scan backward from match.start() to find sentence end or newline
        start_idx = max(0, match.start() - 200) # Look back 200 chars
        preceding_text = answer[start_idx:match.start()].strip()
        
        # Heuristic: Extract the last quote if present
        quote_match = re.search(r'"([^"]+)"', preceding_text)
        quote_text = quote_match.group(1) if quote_match else preceding_text.split('.')[-1].strip()
        
        citations.append({
            "source": source_name,
            "text": quote_text,
            "full_match": match.group(0)
        })
        
    return citations

def find_chunk_by_title(chunks: List[Dict], title: str) -> Optional[Dict]:
    """Find a source chunk by title (fuzzy match)."""
    if not title: 
        return None
        
    normalized_target = title.lower()
    best_match = None
    best_score = 0.0
    
    for chunk in chunks:
        chunk_title = chunk.get('title', '').lower()
        if normalized_target in chunk_title or chunk_title in normalized_target:
            return chunk # Exact substring match
            
        # TODO: Add Levenshtein if needed, for now substring is robust enough
        
    return None

# =============================================================================
# VERIFICATION LOGIC (ENHANCED)
# =============================================================================

def verify_source_accuracy(answer: str, chunks: List[Dict]) -> Tuple[float, List[str]]:
    """
    Layer 1: Exact span matching
    Layer 2: Semantic similarity (embeddings)
    Layer 3: Metadata cross-check
    """
    citations = extract_citations_from_answer(answer)
    if not citations:
        # If no citations but question was DIRECT/QUOTE mode, might be a failure.
        # But here we just return high score to avoid double penalizing (Relevance/Completeness handles it)
        # Unless answer mentions specific facts without citation.
        return 1.0, [] 

    violations = []
    total_score = 0.0
    
    for citation in citations:
        quote_text = citation['text']
        attributed_source = citation['source']
        
        source_chunk = find_chunk_by_title(chunks, attributed_source)
        
        if not source_chunk:
            violations.append(f"wrong_source: '{attributed_source}' not found in retrieved context")
            total_score += 0.0 # Severe penalty
            continue
            
        chunk_content = str(source_chunk.get('content_chunk', ''))
        
        # Layer 1: Exact Match
        if quote_text in chunk_content:
            total_score += 1.0
            continue
            
        # Layer 2: Semantic Similarity
        # Cache embeddings to avoid re-computing? get_embedding handles caching.
        quote_emb = get_embedding(quote_text)
        
        # Check if chunk has embedding
        chunk_emb = source_chunk.get('embedding')
        if not chunk_emb:
             # Fallback: compute it (might be slow, but necessary for Judge)
            chunk_emb = get_embedding(chunk_content)
            
        similarity = cosine_similarity(quote_emb, chunk_emb)
        
        if similarity >= 0.85:
            total_score += 0.9 # Good paraphrase
        elif similarity >= 0.70:
            total_score += 0.6 # Weak paraphrase / Potential hallucination
            violations.append(f"weak_paraphrase: '{quote_text[:30]}...' (sim: {similarity:.2f})")
        else:
            total_score += 0.0 # Fabricated
            violations.append(f"fabricated_quote: '{quote_text[:30]}...' (sim: {similarity:.2f})")
            
    final_score = total_score / len(citations)
    return final_score, violations

def verify_relevance(question: str, answer: str, intent: str) -> Tuple[float, List[str]]:
    """
    Verification using embeddings + intent-specific checks.
    """
    violations = []
    
    # Step 1: Semantic Similarity
    q_emb = get_embedding(question)
    a_emb = get_embedding(answer)
    similarity = cosine_similarity(q_emb, a_emb)
    
    # Boost similarity if it's already high (it's hard to get 1.0 with sentence vs paragraph)
    # 0.75+ is usually very good for QA
    semantic_score = min(1.0, similarity / 0.75) 
    
    # Step 2: Intent Checks
    score_modifier = 1.0
    
    if intent == "DIRECT":
        # Check for definitional markers
        if "nedir" in question.lower() and "tanım" not in answer.lower() and "demektir" not in answer.lower():
             violations.append("missing_definition_format")
             score_modifier *= 0.8
             
    elif intent == "COMPARATIVE":
        # Check for comparison logic
        comparison_markers = ["fark", "benzer", "birincisi", "oysa", "diğer yandan"]
        if not any(m in answer.lower() for m in comparison_markers):
            violations.append("missing_comparison_structure")
            score_modifier *= 0.7
            
    final_score = semantic_score * score_modifier
    return max(0.0, min(1.0, final_score)), violations

def verify_ocr_quality(text: str) -> Tuple[float, List[str]]:
    """
    Multi-stage OCR detection.
    """
    violations = []
    
    # Stage 1: Conservative Regex
    ocr_patterns = [
        (r'\d[a-z]{2,}', 'number_letter_mix'), # 1nsan
        (r'[;:~]{2,}', 'excessive_punctuation'), # ;:
        (r'\bc;', 'ocr_artifact'), 
    ]
    
    regex_penalties = 0.0
    for pattern, name in ocr_patterns:
        if re.search(pattern, text):
            violations.append(name)
            regex_penalties += 0.3
            
    # Stage 2: Fluency (Spell Checker)
    spell_checker = get_spell_checker()
    words = text.split()
    if not words: return 1.0, []
    
    valid_count = sum(1 for w in words if spell_checker.check(w) or w.isnumeric() or len(w) < 3)
    fluency_score = valid_count / len(words)
    
    if fluency_score < 0.80:
        violations.append(f"low_fluency ({fluency_score:.2f})")
    
    # Final calculation
    # Base score comes from fluency, heavily penalized by regex errors
    final_score = fluency_score - regex_penalties
    return max(0.0, final_score), violations

def verify_format(answer: str, mode: str) -> Tuple[float, List[str]]:
    """
    Check if headers exist based on mode.
    """
    violations = []
    expected_headers = []
    
    if mode == 'QUOTE':
        expected_headers = ["Doğrudan Tanımlar", "Bağlamsal Analiz"]
    elif mode == 'HYBRID':
        expected_headers = ["Karşıt Görüşler", "Bağlamsal Kanıtlar"]
        
    missing = [h for h in expected_headers if f"## {h}" not in answer]
    
    if missing:
        violations.append(f"missing_headers: {missing}")
        return 0.5, violations
        
    return 1.0, []

# =============================================================================
# MAIN EVALUATION FUNCTION
# =============================================================================

async def evaluate_answer(
    question: str,
    answer: str,
    chunks: List[Dict],
    answer_mode: str,
    intent: str = "SYNTHESIS"
) -> Dict[str, Any]:
    """
    Evaluate answer quality using Judge AI logic + Auto-Verification.
    Uses Rule-Based Verification mostly to save cost/latency, 
    but structures it as if an AI Judge did it.
    """
    
    # 1. Select Rubric
    rubric = get_rubric_for_question(question, intent)
    
    # 2. Run Verifications
    score_source, viol_source = verify_source_accuracy(answer, chunks)
    score_relevance, viol_relevance = verify_relevance(question, answer, intent)
    score_ocr, viol_ocr = verify_ocr_quality(answer)
    score_format, viol_format = verify_format(answer, answer_mode)
    
    # Completeness is hard to auto-verify without LLM. 
    # For now, we infer it from length and relevance.
    score_completeness = min(1.0, len(answer) / 500.0) * score_relevance
    viol_completeness = []
    if score_completeness < 0.5:
         viol_completeness.append("answer_too_short")

    # 3. Construct Scores Dict
    criterion_scores = {
        "source_accuracy": score_source,
        "relevance": score_relevance,
        "completeness": score_completeness,
        "ocr_correction": score_ocr,
        "format_compliance": score_format
    }
    
    # 4. Calculate Overall & Verdict
    overall_score = calculate_overall_score(criterion_scores, rubric)
    
    # Calculate chunk quality for adaptive threshold
    avg_chunk_quality = sum(c.get('answerability_score', 0) for c in chunks) / max(1, len(chunks))
    
    verdict = get_verdict(overall_score, intent, avg_chunk_quality, criterion_scores)
    
    # 5. Identify Failures & Hints
    failures = identify_failures(criterion_scores, threshold=0.5, rubric=rubric)
    # Add auto-detected violations to failures list for clarity
    for f in failures:
        name = f['criterion']
        if name == 'source_accuracy': f['possible_issues'] = viol_source
        if name == 'relevance': f['possible_issues'] = viol_relevance
        if name == 'ocr_correction': f['possible_issues'] = viol_ocr
        if name == 'format_compliance': f['possible_issues'] = viol_format
        
    hints = generate_hints_from_failures(failures)
    
    return {
        "verdict": verdict,
        "overall_score": overall_score,
        "criterion_scores": criterion_scores,
        "failures": failures,
        "hints_for_retry": hints,
        "metrics": {
            "chunk_quality": avg_chunk_quality,
            "citations_found": len(extract_citations_from_answer(answer))
        }
    }
