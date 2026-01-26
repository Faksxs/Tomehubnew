# -*- coding: utf-8 -*-
import logging
import asyncio
import time
from typing import Dict, List, Any
from services.work_ai_service import generate_work_ai_answer
from services.judge_ai_service import evaluate_answer
from services.epistemic_service import classify_question_intent

logger = logging.getLogger(__name__)

async def generate_evaluated_answer(
    question: str,
    chunks: List[Dict],
    answer_mode: str,
    confidence_score: float,
    max_attempts: int = 2,
    network_status: str = "IN_NETWORK"
) -> Dict[str, Any]:
    """
    Generate and evaluate an answer with automatic quality-based retry.
    """
    start_time = time.time()
    history = []
    
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
    
    # Phase 4: Smart Orchestration (Selective Activation)
    should_audit, reason = should_trigger_audit(confidence_score, intent, network_status)
    if not should_audit:
        logger.info(f"[DualAI] Fast Track Activated ({reason}) - Skipping Judge AI")
        
        # Fast Track Execution (Single Pass)
        try:
            work_result = await generate_work_ai_answer(
                question=question,
                chunks=chunks,
                answer_mode=answer_mode,
                confidence_score=confidence_score,
                feedback_hints=None,
                network_status=network_status
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
            
            return _create_success_response(work_result["answer"], pseudo_evaluation, history, start_time)
            
        except Exception as e:
            logger.error(f"[DualAI] Fast Track failed: {e}")
            return _create_error_response(e)


    # Regular Audit Track (Loop)
    for attempt in range(1, max_attempts + 1):
        step_start = time.time()
        logger.info(f"[DualAI] Attempt {attempt}/{max_attempts} for '{question[:30]}...' (Mode: {answer_mode})")
        
        # 1. Work AI Generation
        try:
            work_result = await generate_work_ai_answer(
                question=question,
                chunks=chunks,
                answer_mode=answer_mode,
                confidence_score=confidence_score,
                feedback_hints=hints,
                network_status=network_status
            )
            answer_text = work_result["answer"]
        except Exception as e:
            logger.error(f"[DualAI] Work AI failed: {e}")
            if attempt < max_attempts:
                continue # Retry
            return _create_error_response(e)
            
        # 2. Judge AI Evaluation
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
            # If Judge fails, we accept the answer but mark as unevaluated
            return _create_fallback_response(answer_text, work_result)
            
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
            return _create_success_response(answer_text, eval_result, history, start_time)
            
        elif verdict == "REGENERATE":
            if attempt < max_attempts:
                # Prepare hints for next attempt
                hints = eval_result["hints_for_retry"]
                logger.info(f"[DualAI] Retrying with hints: {hints}")
                continue
            else:
                # Out of attempts, return best effort or decline
                # If score is very low, decline. If borderline, pass with warning?
                # For now, we return the last answer but with DECLINE status
                return _create_success_response(answer_text, eval_result, history, start_time)
                
        elif verdict == "DECLINE":
             # Immediate failure (e.g. offensive, completely wrong topic)
             # But usually we try at least once more if we haven't retried yet?
             # If score is extremely low (<0.3), maybe stop.
             if eval_result["overall_score"] < 0.3 or attempt >= max_attempts:
                 return _create_success_response(answer_text, eval_result, history, start_time)
             else:
                 hints = eval_result["hints_for_retry"]
                 continue

    # Fallback (should be reached via loop exits)
    last_entry = history[-1]
    return _create_success_response(last_entry["answer"], last_entry["evaluation"], history, start_time)


def should_trigger_audit(confidence: float, intent: str, network_status: str) -> tuple:
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
        
    # Rule 3: Fast Track for High Confidence + Simple Intent
    if confidence >= 5.5 and intent == "DIRECT":
        return False, "High Confidence Direct Answer"
        
    # Rule 4: Audit Low Confidence
    if confidence < 4.0:
        return True, "Low Confidence Data"
        
    # Default: Fast Track (Optimistic by default for In-Network)
    return False, "Standard In-Network Query"


def _create_success_response(answer, evaluation, history, start_time):
    return {
        "final_answer": answer,
        "metadata": {
            "verdict": evaluation["verdict"],
            "quality_score": evaluation["overall_score"],
            "attempts": len(history),
            "total_latency_ms": (time.time() - start_time) * 1000,
            "history": history
        }
    }

def _create_error_response(error):
    return {
        "final_answer": "Üzgünüm, bir teknik hata oluştu. Lütfen tekrar deneyin.",
        "metadata": {
            "verdict": "ERROR",
            "error": str(error)
        }
    }

def _create_fallback_response(answer, work_result):
    return {
        "final_answer": answer,
        "metadata": {
            "verdict": "UNEVALUATED",
            "quality_score": 0.0,
            "note": "Judge AI failed, returning raw answer"
        }
    }
