# -*- coding: utf-8 -*-
import os
import json
import re
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple
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
from services.monitoring import JUDGE_SCORE

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

def extract_citations_from_answer(answer: str, chunks: List[Dict] = None) -> List[Dict[str, Any]]:
    """
    Extract citations from answer text.
    Supports both legacy [Kaynak: Title] and new [ID: X] formats.
    """
    citations = []
    
    # Pattern 1: [ID: X] (Preferred for Explorer Mode)
    id_matches = re.finditer(r'\[ID:\s*(\d+)\]', answer)
    for match in id_matches:
        try:
            source_id = int(match.group(1))
            # Find the sentence preceding this ID
            start_idx = max(0, match.start() - 200)
            preceding_text = answer[start_idx:match.start()].strip().split('\n')[-1] # Only last line
            
            citations.append({
                "source_id": source_id,
                "text": preceding_text,
                "full_match": match.group(0),
                "type": "ID"
            })
        except:
            continue

    # Pattern 2: [Kaynak: Title] (Legacy support)
    source_matches = re.finditer(r'\[Kaynak:\s*(.*?)\]', answer)
    for match in source_matches:
        source_name = match.group(1).strip()
        start_idx = max(0, match.start() - 200)
        preceding_text = answer[start_idx:match.start()].strip().split('\n')[-1]
        
        citations.append({
            "source": source_name,
            "text": preceding_text,
            "full_match": match.group(0),
            "type": "LEGACY"
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
    Check if citations point to correct chunks and contain accurate info.
    """
    citations = extract_citations_from_answer(answer, chunks)
    if not citations:
        # PENALTY: No citations = no way to verify source accuracy
        return 0.6, ["no_citations_for_verification"]

    violations = []
    total_score = 0.0
    
    for citation in citations:
        quote_text = citation['text']
        
        # Determine source chunk
        source_chunk = None
        if citation['type'] == 'ID':
            idx = citation['source_id'] - 1
            if 0 <= idx < len(chunks):
                source_chunk = chunks[idx]
        else:
            source_chunk = find_chunk_by_title(chunks, citation['source'])
        
        if not source_chunk:
            violations.append(f"wrong_source: {citation.get('source', 'ID:'+str(citation.get('source_id')))} not found")
            total_score += 0.0
            continue
            
        chunk_content = str(source_chunk.get('content_chunk', '')).lower()
        quote_lower = quote_text.lower()
        
        # Layer 1: Exact Match (Partial)
        # Often LLM rephrases slightly, so we look for 10-word spans
        words = quote_lower.split()
        if len(words) > 5:
            match_found = False
            for start in range(len(words) - 5):
                span = " ".join(words[start:start+5])
                if span in chunk_content:
                    match_found = True
                    break
            if match_found:
                total_score += 1.0
                continue
            
        # Layer 2: Semantic Similarity
        quote_emb = get_embedding(quote_text)
        chunk_emb = source_chunk.get('embedding') or get_embedding(chunk_content)
        similarity = cosine_similarity(quote_emb, chunk_emb)
        
        if similarity >= 0.82:
            total_score += 0.9
        elif similarity >= 0.65:
            total_score += 0.5
            violations.append(f"hallucination_risk: '{quote_text[:30]}...' (sim: {similarity:.2f})")
        else:
            total_score += 0.0
            violations.append(f"fabricated_quote: '{quote_text[:30]}...'")
            
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
    
    # NOTE: Don't inflate the score - use raw similarity with realistic ceiling
    # 0.85+ is excellent, 0.75+ is good, below is weak
    if similarity >= 0.85:
        semantic_score = 1.0
    elif similarity >= 0.70:
        semantic_score = 0.7 + (similarity - 0.70) * 2  # 0.70->0.7, 0.85->1.0
    else:
        semantic_score = similarity  # Raw score for weak matches
    
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
    
    valid_count = sum(1 for w in words if (spell_checker.loaded and w.lower() in spell_checker.vocab) or w.isnumeric() or len(w) < 3)
    fluency_score = valid_count / len(words)
    
    if fluency_score < 0.80:
        violations.append(f"low_fluency ({fluency_score:.2f})")
    
    # Final calculation
    # Base score comes from fluency, heavily penalized by regex errors
    final_score = fluency_score - regex_penalties
    return max(0.0, final_score), violations

def verify_synthesis_depth(answer: str, chunks: List[Dict], mode: str) -> Tuple[float, List[str]]:
    """
    Check if the answer adds value (synthesis) or just paraphrases.
    Only strictly applied for EXPLORER and SYNTHESIS modes.
    """
    if mode not in ['EXPLORER', 'SYNTHESIS']:
        return 1.0, []
        
    violations = []
    
    # 1. Verbatim Ratio Check
    # How much of the answer is exact sentences from chunks?
    chunk_texts = [str(c.get('content_chunk', '')).lower() for c in chunks]
    sentences = re.split(r'[.!?]\s+', answer)
    total_sentences = len(sentences)
    verbatim_count = 0
    
    for sent in sentences:
        if len(sent) < 20: continue # Skip short fragments
        if any(sent.lower() in chunk_text for chunk_text in chunk_texts):
            verbatim_count += 1
            
    verbatim_ratio = verbatim_count / max(1, total_sentences)
    
    # 2. Connector Words Check (Dialectical Depth)
    dialectical_connectors = [
        'dolayısıyla', 'ilişkili', 'çelişki', 'paradoks', 'sentez', 
        'bağlamında', 'fakat', 'oysaki', 'öte yandan', 'bu durum',
        'relationship', 'correlation', 'however', 'context', 'synthesis'
    ]
    connector_count = sum(1 for w in dialectical_connectors if w in answer.lower())
    
    # 3. Scoring
    # Base depth score
    # High verbatim ratio reduces score
    # High connector count increases score
    
    # 3. Scoring
    # Base depth score now starts lower to mandate "value-add"
    # High verbatim ratio reduces score
    # High connector count increases score
    
    base_score = 0.8 # Start lower, require connectors to gain score
    
    if verbatim_ratio > 0.8: # Extreme copy-pasting
        base_score *= 0.3 # Heavy penalty
        violations.append("ossified_content: too high verbatim ratio")
    elif verbatim_ratio > 0.4: # Lowered threshold for paraphrase detection
        base_score *= 0.6
        violations.append("shallow_synthesis: high paraphrasing, low value-add")
        
    if connector_count >= 5:
        base_score += 0.2 # Bonus for deep synthesis language
    elif connector_count < 3 and mode == 'EXPLORER':
        base_score *= 0.7
        violations.append("low_dialectical_depth: missing reasoning connectors")
        
    return max(0.0, min(1.0, base_score)), violations

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
        return 0.4, violations  # Stricter penalty for missing headers
        
    return 0.9, []  # Don't give perfect 1.0 for just having headers

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
    score_depth, viol_depth = verify_synthesis_depth(answer, chunks, answer_mode)
    
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
        "format_compliance": score_format,
        "synthesis_depth": score_depth
    }
    
    # 4. Calculate Overall & Verdict
    overall_score = calculate_overall_score(criterion_scores, rubric)
    
    avg_chunk_quality = sum(c.get('answerability_score', 0) for c in chunks) / max(1, len(chunks))
    verdict = get_verdict(overall_score, intent, avg_chunk_quality, criterion_scores)
    
    # 5. Identify Failures & Hints
    failures = identify_failures(criterion_scores, threshold=0.5, rubric=rubric)
    for f in failures:
        name = f['criterion']
        if name == 'source_accuracy': f['possible_issues'] = viol_source
        if name == 'relevance': f['possible_issues'] = viol_relevance
        if name == 'ocr_correction': f['possible_issues'] = viol_ocr
        if name == 'format_compliance': f['possible_issues'] = viol_format
        if name == 'synthesis_depth': f['possible_issues'] = viol_depth
        
    hints = generate_hints_from_failures(failures)
    
    # [Observability] Record Metric
    # Intent and Netowrk Status are passed in, verify context
    # Note: 'network_status' is not passed to evaluate_answer currently, defaulting to "UNKNOWN" if missing
    # But wait, evaluate_answer signature: (question, answer, chunks, answer_mode, intent)
    # Orchestrator has network_status. We should probably pass it or infer it.
    # For now, let's use a safe default or ask to update signature. 
    # Actually Orchestrator calls this. Let's keep it simple and record partially.
    # Actually, we can get better context if we move the recording to Orchestrator?
    # No, keep it close to logic. 
    try:
        # We need to map verdict (PASS/REGENERATE) from the result
        # verdict is in result['verdict']
        verdict_val = verdict.upper() if verdict else "UNKNOWN"
        JUDGE_SCORE.labels(
            intent=intent, 
            network_status="UNKNOWN", 
            verdict=verdict_val
        ).observe(overall_score)
    except Exception as e:
        logger.warning(f"Failed to record metric: {e}")

    return {
        "verdict": verdict,
        "overall_score": overall_score,
        "criterion_scores": criterion_scores,
        "failures": failures,
        "hints_for_retry": hints,
        "metrics": {
            "chunk_quality": avg_chunk_quality,
            "citations_found": len(extract_citations_from_answer(answer, chunks)),
            "synthesis_ratio": score_depth
        }
    }

