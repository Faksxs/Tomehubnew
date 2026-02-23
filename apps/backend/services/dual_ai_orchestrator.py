# -*- coding: utf-8 -*-
import logging
import asyncio
import time
from typing import Dict, List, Any
from config import settings
from services.work_ai_service import generate_work_ai_answer
from services.judge_ai_service import evaluate_answer
from services.epistemic_service import classify_question_intent

logger = logging.getLogger(__name__)

# Overall timeout budgets per answer mode (seconds)
TIMEOUT_BUDGET = {
    "SYNTHESIS": 5.0,       # Fast synthesis
    "QUOTE": 3.0,           # Shortest
    "DIRECT": 3.0,          # Direct lookup
    "CITATION_SEEKING": 2.5,  # Quick reference finding
    "FOLLOW_UP": 4.0,       # Follow-up (with context)
    "COMPARATIVE": 7.0,     # Comparison needs analysis
    "EXPLORER": 25.0,       # Exploratory (max time)
    "NARRATIVE": 6.0,       # Narrative building
    "SOCIETAL": 8.0,        # Complex societal analysis
}

async def generate_evaluated_answer(
    question: str,
    chunks: List[Dict],
    answer_mode: str,
    confidence_score: float,
    max_attempts: int = 2,
    network_status: str = "IN_NETWORK",
    conversation_state: Dict[str, Any] = None,
    source_diversity_count: int = 0,
) -> Dict[str, Any]:
    """
    Generate and evaluate an answer with automatic quality-based retry.
    
    NOTE: Critical timeout gates prevent hanging queries:
    - Single answer generation: answer_mode-specific timeout
    - Overall orchestration: budget-based timeout
    """
    start_time = time.time()
    history = []
    
    # Get timeout budget for this answer mode
    overall_timeout_s = TIMEOUT_BUDGET.get(answer_mode or "SYNTHESIS", 5.0)
    
    # Pre-detect intent for consistency across Work/Judge (with caching)
    try:
        from services.cache_service import get_cache, generate_cache_key
        from config import settings
        
        cache = get_cache()
        intent = None
        complexity = None
        
        # Check cache for intent classification
        if cache:
            cache_key = generate_cache_key(
                service="intent",
                query=question,
                firebase_uid="",  # Intent is question-only, not user-specific
                book_id=None,
                limit=1,
                version=settings.LLM_MODEL_VERSION
            )
            cached_result = cache.get(cache_key)
            if cached_result:
                intent, complexity = cached_result
                logger.info(f"Cache hit for intent classification: {intent}")
        
        # If not cached, classify and cache
        if intent is None:
            intent, complexity = classify_question_intent(question)
            
            # Cache the result (TTL: 1 hour = 3600 seconds)
            if cache:
                cache_key = generate_cache_key(
                    service="intent",
                    query=question,
                    firebase_uid="",
                    book_id=None,
                    limit=1,
                    version=settings.LLM_MODEL_VERSION
                )
                cache.set(cache_key, (intent, complexity), ttl=3600)
                logger.info(f"Cached intent classification: {intent}")
    except Exception as e:
        logger.warning(f"Intent classification failed: {e}")
        intent = "SYNTHESIS"
        complexity = "LOW"
        
    hints = None
    fallback_state: Dict[str, Any] = {"pro_fallback_used": 0}
    
    # Phase 4: Smart Orchestration (Selective Activation)
    should_audit, reason = should_trigger_audit(
        confidence_score,
        intent,
        network_status,
        source_diversity_count=source_diversity_count,
    )
    effective_max_attempts = max_attempts
    if answer_mode == "EXPLORER":
        # De-risked latency policy: Explorer runs single-pass by default.
        # Only escalate to configured retry count for clearly high-risk cases.
        effective_max_attempts = 1
        if should_audit and (
            network_status in {"OUT_OF_NETWORK", "HYBRID"}
            or intent == "COMPARATIVE"
            or confidence_score < 3.8
        ):
            effective_max_attempts = max(1, min(int(max_attempts or 1), 2))
    if not should_audit:
        logger.info(f"[DualAI] Fast Track Activated ({reason}) - Skipping Judge AI")
        
        # Fast Track Execution (Single Pass) with timeout
        try:
            # Apply timeout gate to prevent hanging
            work_result = await asyncio.wait_for(
                generate_work_ai_answer(
                    question=question,
                    chunks=chunks,
                    answer_mode=answer_mode,
                    confidence_score=confidence_score,
                    feedback_hints=None,
                    network_status=network_status,
                    conversation_state=conversation_state,
                    allow_pro_fallback=False,
                    fallback_state=fallback_state,
                ),
                timeout=overall_timeout_s
            )
            
            # Construct a "SKIPPED_GOOD" verification result
            pseudo_evaluation = {
                "verdict": "SKIPPED_GOOD",
                "overall_score": 1.0, # Assumed perfect
                "criterion_scores": {},
                "failures": [],
                "hints_for_retry": [],
                "explanation": f"Audit skipped: {reason}"
            }
            
            history.append({
                "attempt": 1,
                "answer": work_result["answer"],
                "evaluation": pseudo_evaluation,
                "latency": (time.time() - start_time) * 1000
            })
            
            return _create_success_response(
                work_result["answer"],
                pseudo_evaluation,
                history,
                start_time,
                work_result=work_result,
                judge_used=False,
                max_attempts_configured=max_attempts,
                max_attempts_effective=effective_max_attempts,
                source_diversity_count=source_diversity_count,
            )
            
        except Exception as e:
            logger.error(f"[DualAI] Fast Track failed: {e}")
            return _create_error_response(
                e,
                max_attempts_configured=max_attempts,
                max_attempts_effective=effective_max_attempts
            )


    # Regular Audit Track (Loop)
    # Refactored for Explorer Timeout Support
    async def _execute_audit_track():
        current_hints = hints
        for attempt in range(1, effective_max_attempts + 1):
            step_start = time.time()
            logger.info(f"[DualAI] Attempt {attempt}/{effective_max_attempts} for '{question[:30]}...' (Mode: {answer_mode})")
            
            # 1. Work AI Generation
            logger.info(f"[DualAI] Starting Work AI Generation (Attempt {attempt})")
            try:
                # Apply timeout gate with remaining budget
                elapsed = time.time() - start_time
                remaining_timeout = max(1.0, overall_timeout_s - elapsed)
                
                work_result = await asyncio.wait_for(
                    generate_work_ai_answer(
                        question=question,
                        chunks=chunks,
                        answer_mode=answer_mode,
                        confidence_score=confidence_score,
                        feedback_hints=current_hints,
                        network_status=network_status,
                        conversation_state=conversation_state,
                        allow_pro_fallback=(attempt == effective_max_attempts and bool(current_hints)),
                        fallback_state=fallback_state,
                    ),
                    timeout=remaining_timeout
                )
                answer_text = work_result["answer"]
            except asyncio.TimeoutError:
                logger.error(f"[DualAI] Work AI timeout after {time.time() - start_time:.2f}s (Attempt {attempt})")
                if attempt < effective_max_attempts:
                    continue  # Retry with timeout-aware fallback
                return _create_error_response(
                    TimeoutError(f"LLM generation timeout exceeded ({overall_timeout_s}s budget)"),
                    max_attempts_configured=max_attempts,
                    max_attempts_effective=effective_max_attempts
                )
            except Exception as e:
                logger.error(f"[DualAI] Work AI failed: {e}")
                if attempt < effective_max_attempts:
                    continue # Retry
                return _create_error_response(
                    e,
                    max_attempts_configured=max_attempts,
                    max_attempts_effective=effective_max_attempts
                )
                
            # 2. Judge AI Evaluation
            logger.info(f"[DualAI] Starting Judge AI Evaluation (Attempt {attempt})")
            try:
                eval_result = await evaluate_answer(
                    question=question,
                    answer=answer_text,
                    chunks=chunks,
                    answer_mode=answer_mode,
                    intent=intent
                )
            except Exception as e:
                logger.error(f"[DualAI] Judge AI failed: {e}")
                return _create_fallback_response(
                    answer_text,
                    work_result,
                    attempts=len(history),
                    max_attempts_configured=max_attempts,
                    max_attempts_effective=effective_max_attempts
                )
                
            step_latency = (time.time() - step_start) * 1000
            
            # Log result
            logger.info(f"[DualAI] Verdict: {eval_result['verdict']} | Score: {eval_result['overall_score']:.2f}")
            
            history.append({
                "attempt": attempt,
                "answer": answer_text,
                "evaluation": eval_result,
                "latency": step_latency
            })
            
            # 3. Decision Logic
            verdict = eval_result["verdict"]
            
            if verdict == "PASS":
                return _create_success_response(
                    answer_text,
                    eval_result,
                    history,
                    start_time,
                    work_result=work_result,
                    judge_used=True,
                    max_attempts_configured=max_attempts,
                    max_attempts_effective=effective_max_attempts,
                    source_diversity_count=source_diversity_count,
                )
                
            elif verdict == "REGENERATE":
                if attempt < effective_max_attempts:
                    current_hints = eval_result["hints_for_retry"]
                    logger.info(f"[DualAI] Retrying with hints: {current_hints}")
                    continue
                else:
                    return _create_success_response(
                        answer_text,
                        eval_result,
                        history,
                        start_time,
                        work_result=work_result,
                        judge_used=True,
                        max_attempts_configured=max_attempts,
                        max_attempts_effective=effective_max_attempts
                    )
                    
            elif verdict == "DECLINE":
                 if eval_result["overall_score"] < 0.3 or attempt >= effective_max_attempts:
                     return _create_success_response(
                         answer_text,
                         eval_result,
                         history,
                         start_time,
                         work_result=work_result,
                         judge_used=True,
                         max_attempts_configured=max_attempts,
                         max_attempts_effective=effective_max_attempts
                     )
                 else:
                     current_hints = eval_result["hints_for_retry"]
                     continue

        # Fallback (should be reached via loop exits)
        last_entry = history[-1]
        return _create_success_response(
            last_entry["answer"],
            last_entry["evaluation"],
            history,
            start_time,
            work_result=work_result,
            judge_used=True,
            max_attempts_configured=max_attempts,
            max_attempts_effective=effective_max_attempts
        )

    # Execute with Timeout for Explorer Mode
    if answer_mode == 'EXPLORER':
        try:
            # Keep Explorer responsive; long tails are handled via fallback path.
            return await asyncio.wait_for(_execute_audit_track(), timeout=24.0)
        except asyncio.TimeoutError:
            logger.warning("[DualAI] Explorer Mode TIMEOUT (24s). Falling back to Standard Synthesis.")
            
            # Fallback: Run standard synthesis (Fast & Reliable)
            # We treat this as a "system fallback"
            fallback_result = await generate_work_ai_answer(
                question=question,
                chunks=chunks,
                answer_mode='SYNTHESIS', # Fallback to Standard
                confidence_score=confidence_score,
                network_status=network_status
            )
            
            # Create a synthetic "Timeout" evaluation
            fallback_eval = {
                "verdict": "FALLBACK_TIMEOUT",
                "overall_score": 0.5,
                "criterion_scores": {},
                "failures": ["Timeout in Explorer Mode"],
                "hints_for_retry": [],
                "explanation": "Explorer mode time limit exceeded. Answer generated via Standard mode."
            }
            
            # Append note to answer
            final_ans = fallback_result["answer"] + "\n\n(Not: Derin analiz zaman aşımına uğradığı için standart özet sunulmaktadır.)"
            
            history.append({
                "attempt": 1, 
                "answer": final_ans,
                "evaluation": fallback_eval,
                "latency": (time.time() - start_time) * 1000
            })
            
            return _create_success_response(
                final_ans,
                fallback_eval,
                history,
                start_time,
                work_result=fallback_result,
                judge_used=False,
                max_attempts_configured=max_attempts,
                max_attempts_effective=effective_max_attempts,
                source_diversity_count=source_diversity_count,
            )
            
    else:
        # Standard execution (no extra timeout wrapper, let global timeout handle it)
        return await _execute_audit_track()


def should_trigger_audit(confidence: float, intent: str, network_status: str, source_diversity_count: int = 0) -> tuple:
    """
    Decide whether to trigger the expensive Judge AI audit.
    
    Returns:
        (should_audit: bool, reason: str)
    """
    # Rule 1: Always audit OUT_OF_NETWORK (High Hallucination Risk)
    if network_status == "OUT_OF_NETWORK":
        return True, "Out of Network Risk"
        
    # Rule 2: Always audit HYBRID / Complex synthesis
    if network_status == "HYBRID" or intent == "COMPARATIVE":
        return True, "Complex Synthesis Required"

    if bool(getattr(settings, "L3_JUDGE_DIVERSITY_AUDIT_ENABLED", False)):
        threshold = int(getattr(settings, "L3_JUDGE_DIVERSITY_THRESHOLD", 2) or 2)
        if int(source_diversity_count or 0) < max(1, threshold):
            return True, "Low Source Diversity"
        
    # Rule 3: Fast Track for High Confidence + Simple Intent
    # Confidence is capped to 5.0 in retrieval context, so threshold must be reachable.
    if confidence >= 4.5 and intent in {"DIRECT", "FOLLOW_UP"}:
        return False, "High Confidence Direct Answer"
        
    # Rule 4: Audit Low Confidence
    if confidence < 4.0:
        return True, "Low Confidence Data"
        
    # Default: Fast Track (Optimistic by default for In-Network)
    return False, "Standard In-Network Query"


def _create_success_response(
    answer,
    evaluation,
    history,
    start_time,
    work_result=None,
    judge_used=True,
    max_attempts_configured=2,
    max_attempts_effective=2,
    source_diversity_count=0,
):
    total_latency_ms = (time.time() - start_time) * 1000
    used_chunks = []
    work_meta = {}
    if isinstance(work_result, dict):
        work_meta = work_result.get("metadata") or {}
        used_chunks = work_meta.get("chunks", [])
    return {
        "final_answer": answer,
        "metadata": {
            "verdict": evaluation["verdict"],
            "quality_score": evaluation["overall_score"],
            "attempts": len(history),
            "total_latency_ms": total_latency_ms,
            "history": history,
            "used_chunks": used_chunks,
            "audit_cost_profile": {
                "attempts": len(history),
                "max_attempts_configured": max_attempts_configured,
                "max_attempts_effective": max_attempts_effective,
                "total_latency_ms": total_latency_ms,
                "judge_used": bool(judge_used),
            },
            "source_diversity_count": int(source_diversity_count or 0),
            "graph_bridge_attempted": bool(work_meta.get("graph_bridge_attempted", False)),
            "graph_bridge_used": bool(work_meta.get("graph_bridge_used", False)),
            "graph_bridge_timeout": bool(work_meta.get("graph_bridge_timeout", False)),
        },
    }


def _create_error_response(error, max_attempts_configured=2, max_attempts_effective=2):
    return {
        "final_answer": "Uzgunum, bir teknik hata olustu. Lutfen tekrar deneyin.",
        "metadata": {
            "verdict": "ERROR",
            "error": str(error),
            "audit_cost_profile": {
                "attempts": 0,
                "max_attempts_configured": max_attempts_configured,
                "max_attempts_effective": max_attempts_effective,
                "total_latency_ms": 0.0,
                "judge_used": False,
            },
        },
    }


def _create_fallback_response(answer, work_result, attempts=1, max_attempts_configured=2, max_attempts_effective=2):
    used_chunks = []
    if isinstance(work_result, dict):
        used_chunks = (work_result.get("metadata") or {}).get("chunks", [])
    return {
        "final_answer": answer,
        "metadata": {
            "verdict": "UNEVALUATED",
            "quality_score": 0.0,
            "note": "Judge AI failed, returning raw answer",
            "used_chunks": used_chunks,
            "audit_cost_profile": {
                "attempts": attempts,
                "max_attempts_configured": max_attempts_configured,
                "max_attempts_effective": max_attempts_effective,
                "total_latency_ms": 0.0,
                "judge_used": False,
            },
        },
    }
