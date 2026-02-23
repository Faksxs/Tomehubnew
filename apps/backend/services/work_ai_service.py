# -*- coding: utf-8 -*-
import os
import json
import asyncio
import logging
import time
from typing import List, Optional, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

from config import settings
from services.epistemic_service import get_prompt_for_mode, build_epistemic_context
from services.llm_client import (
    MODEL_TIER_FLASH,
    ROUTE_MODE_DEFAULT,
    ROUTE_MODE_EXPLORER_QWEN_PILOT,
    generate_text,
    get_model_for_tier,
)

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

def _format_conversation_state(state: Dict[str, Any]) -> str:
    """
    Format structured conversation state into readable context for the LLM.
    Enables the AI to be aware of ongoing discussion context.
    """
    parts = ["📊 KONUŞMA DURUMU (Önceki Turlardan):"]
    
    # Active topic
    if state.get('active_topic'):
        parts.append(f"📍 Aktif Konu: {state['active_topic']}")
    
    # Assumptions (warn AI not to treat as facts)
    assumptions = state.get('assumptions', [])
    if assumptions:
        parts.append("\n⚠️ AKTİF VARSAYIMLAR (Gerçek olarak SUNMA):")
        for a in assumptions[:5]:  # Limit to 5 most recent
            conf = a.get('confidence', 'MEDIUM')
            text = a.get('text', '')
            parts.append(f"  • [{conf}] {text}")
    
    # Established facts
    facts = state.get('established_facts', [])
    if facts:
        parts.append("\n✓ DOĞRULANMIŞ BİLGİLER (Kaynaklı):")
        for f in facts[:5]:
            text = f.get('text', '')
            source = f.get('source', 'Bilinmeyen')
            parts.append(f"  • {text} [Kaynak: {source}]")
    
    # Open questions
    questions = state.get('open_questions', [])
    if questions:
        parts.append("\n❓ AÇIK SORULAR:")
        for q in questions[:3]:
            parts.append(f"  • {q}")
    
    # Turn count for context
    turn_count = state.get('turn_count', 0)
    if turn_count > 0:
        parts.append(f"\n[Bu konuşmanın {turn_count}. turu]")
    
    return "\n".join(parts)


@retry(
    stop=stop_after_attempt(2), 
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def generate_work_ai_answer(
    question: str,
    chunks: List[Dict],
    answer_mode: str,
    confidence_score: float,
    feedback_hints: Optional[List[str]] = None,
    network_status: str = "IN_NETWORK",
    conversation_state: Optional[Dict[str, Any]] = None,
    allow_pro_fallback: bool = False,
    fallback_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate an answer using Flash with optional Pro fallback.
    
    Args:
        question: User's question
        chunks: Retrieved and classified chunks
        answer_mode: QUOTE | SYNTHESIS | HYBRID | EXPLORER
        confidence_score: Data quality score (0-7)
        feedback_hints: Optional hints from Judge AI for retry
        network_status: IN_NETWORK | OUT_OF_NETWORK | HYBRID
        conversation_state: Structured state from previous conversation turns
        
        Returns:
        {
            "answer": "Generated answer text",
            "metadata": {
                "model": "dynamic",
                "mode": answer_mode,
                "hints_used": bool
            }
        }
    """
    try:
        # 1. Build Context
        context_str, used_chunks = build_epistemic_context(chunks, answer_mode)
        graph_bridge_attempted = False
        graph_bridge_used = False
        graph_bridge_timeout = False
        graph_bridge_latency_ms = 0.0
        graph_bridge_text = ""

        if answer_mode == 'EXPLORER' and bool(getattr(settings, "SEARCH_GRAPH_BRIDGE_EXPLORER_ALWAYS_ATTEMPT", False)):
            graph_bridge_attempted = True
            bridge_started = time.perf_counter()
            timeout_sec = max(
                0.05,
                float(getattr(settings, "SEARCH_GRAPH_BRIDGE_EXPLORER_TIMEOUT_MS", 950)) / 1000.0,
            )
            try:
                from services.search_service import get_graph_enriched_context
                graph_bridge_text = await asyncio.wait_for(
                    asyncio.to_thread(get_graph_enriched_context, chunks, ""),
                    timeout=timeout_sec,
                )
                graph_bridge_text = str(graph_bridge_text or "").strip()
                if graph_bridge_text:
                    graph_bridge_used = True
                    context_str = f"{graph_bridge_text}\n\n{context_str}"
            except asyncio.TimeoutError:
                graph_bridge_timeout = True
            except Exception as bridge_err:
                logger.warning("Explorer graph bridge skipped: %s", bridge_err)
            finally:
                graph_bridge_latency_ms = (time.perf_counter() - bridge_started) * 1000.0
        
        # 1.5 Inject conversation state for Explorer mode
        if answer_mode == 'EXPLORER' and conversation_state and conversation_state.get('active_topic'):
            state_context = _format_conversation_state(conversation_state)
            context_str = f"{state_context}\n\n---\n\n{context_str}"
        
        # 2. Get Base Prompt
        prompt = get_prompt_for_mode(answer_mode, context_str, question, confidence_score, network_status=network_status)
        
        # ... (rest of the logic) ...
        
        # Returns:
        # {
        #     "answer": content,
        #     "metadata": {
        #         "model": "dynamic",
        #         "mode": answer_mode,
        #         "chunks": used_chunks # <--- NEW
        #     }
        # }        
        # 3. Inject Feedback Hints (if retry)
        if feedback_hints:
            hint_block = "\n\n⚠️ ÖNCEKI CEVAP YETERSİZDİ. ŞU NOKTALARA DİKKAT ET VE CEVABI YENİDEN YAZ:\n" 
            hint_block += "\n".join(f"- {h}" for h in feedback_hints)
            hint_block += "\n\nBu uyarılara göre cevabı DÜZELTEREK ve GELİŞTİREREK tekrar oluştur.\n"
            
            # Insert hints before the final instruction
            if "CEVAP:" in prompt:
                prompt = prompt.replace("CEVAP:", f"{hint_block}\nCEVAP:")
            else:
                prompt += hint_block
                
        # 4. Generate Content
        route_mode = ROUTE_MODE_DEFAULT
        provider_hint = None
        allow_secondary_fallback = False
        model = get_model_for_tier(MODEL_TIER_FLASH)
        effective_allow_pro_fallback = allow_pro_fallback

        if answer_mode == 'EXPLORER' and settings.LLM_EXPLORER_QWEN_PILOT_ENABLED:
            route_mode = ROUTE_MODE_EXPLORER_QWEN_PILOT
            provider_hint = settings.LLM_EXPLORER_PRIMARY_PROVIDER
            model = settings.LLM_EXPLORER_PRIMARY_MODEL
            allow_secondary_fallback = True
            # Explorer pilot path uses Qwen primary and Gemini fallback.
            effective_allow_pro_fallback = False
        
        # Adjust temperature based on mode
        # QUOTE/DIRECT needs lower temp for precision
        # SYNTHESIS needs higher temp for creativity
        # EXPLORER needs high temp for dialectical thinking
        if answer_mode == 'QUOTE':
            temperature = 0.3 
        elif answer_mode == 'EXPLORER':
            temperature = 0.7
        else:
            temperature = 0.5 # Default Synthesis
        
        # Explorer tuning: Allow comprehensive dialectical analysis
        # Standard uses 2800, Explorer needs more room for multi-stage reasoning
        max_output_tokens = 2048
        # CRITICAL: Default timeout for all modes to prevent hangs
        # Baseline: 3s for SYNTHESIS (most common), 16s for EXPLORER
        llm_timeout_s = 3.0  # Timeout for SYNTHESIS, QUOTE, CITATION_SEEKING, etc.
        
        if answer_mode == 'EXPLORER':
            max_output_tokens = 3000  # Allow full dialectical response structure
            llm_timeout_s = 16.0  # Proportional timeout increase for EXPLORER
        elif answer_mode == 'CITATION_SEEKING':
            llm_timeout_s = 2.5  # CITATION_SEEKING is usually quick
        elif answer_mode == 'COMPARATIVE':
            llm_timeout_s = 5.0  # COMPARATIVE needs more time for analysis

        result = await asyncio.to_thread(
            generate_text,
            model=model,
            prompt=prompt,
            task="work_ai_answer",
            model_tier=MODEL_TIER_FLASH,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type=None,
            timeout_s=llm_timeout_s,
            allow_pro_fallback=effective_allow_pro_fallback,
            fallback_state=fallback_state,
            provider_hint=provider_hint,
            route_mode=route_mode,
            allow_secondary_fallback=allow_secondary_fallback,
        )
        
        answer_text = result.text.strip()
        
        return {
            "answer": answer_text,
            "metadata": {
                "model": result.model_used,
                "model_tier": result.model_tier,
                "provider_name": result.provider_name,
                "model_fallback_applied": bool(result.fallback_applied),
                "secondary_fallback_applied": bool(result.secondary_fallback_applied),
                "fallback_reason": result.fallback_reason,
                "mode": answer_mode,
                "temperature": temperature,
                "hints_used": bool(feedback_hints),
                "chunks": used_chunks,
                "graph_bridge_attempted": graph_bridge_attempted,
                "graph_bridge_used": graph_bridge_used,
                "graph_bridge_timeout": graph_bridge_timeout,
                "graph_bridge_latency_ms": graph_bridge_latency_ms,
            }
        }
        
    except Exception as e:
        logger.error(f"[Work AI] Generation failed: {e}")
        raise e

if __name__ == "__main__":
    # Simple test
    async def test():
        print("Testing Work AI...")
        # Mock data would be needed here
        pass
    
    # asyncio.run(test())
