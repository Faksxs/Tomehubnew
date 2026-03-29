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
from services.domain_policy_service import DOMAIN_MODE_AUTO
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


def _infer_domain_mode_from_chunks(chunks: List[Dict[str, Any]]) -> str:
    for chunk in chunks or []:
        mode = str(chunk.get("_domain_mode_resolved") or "").strip().upper()
        if mode:
            return mode
    return DOMAIN_MODE_AUTO

def _format_conversation_state(state: Dict[str, Any]) -> str:
    """
    Format structured conversation state into readable context for the LLM.
    Enables the AI to be aware of ongoing discussion context.
    """
    parts = ["KONUSMA DURUMU (Onceki turlardan):"]
    
    # Active topic
    if state.get('active_topic'):
        parts.append(f"Aktif konu: {state['active_topic']}")
    
    # Assumptions (warn AI not to treat as facts)
    assumptions = state.get('assumptions', [])
    if assumptions:
        parts.append("\nAKTIF VARSAYIMLAR (Gercek olarak sunma):")
        for a in assumptions[:5]:  # Limit to 5 most recent
            conf = a.get('confidence', 'MEDIUM')
            text = a.get('text', '')
            parts.append(f"  - [{conf}] {text}")
    
    # Established facts
    facts = state.get('established_facts', [])
    if facts:
        parts.append("\nDOGRULANMIS BILGILER (Kaynakli):")
        for f in facts[:5]:
            text = f.get('text', '')
            source = f.get('source', 'Bilinmeyen')
            parts.append(f"  - {text} [Kaynak: {source}]")
    
    # Open questions
    questions = state.get('open_questions', [])
    if questions:
        parts.append("\nACIK SORULAR:")
        for q in questions[:3]:
            parts.append(f"  - {q}")
    
    # Turn count for context
    turn_count = state.get('turn_count', 0)
    if turn_count > 0:
        parts.append(f"\n[Bu konusmanin {turn_count}. turu]")
    
    return "\n".join(parts)


from services.genkit_telemetry import ai, track_l3_call, z

# ... existing imports ...

@track_l3_call("generate_work_ai_answer")
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
    # Logic remains the same, but now it's tracked by Genkit
    async def _internal_logic():
        try:
            # 1. Build Context
            # Use ai.run to track the context building step
            context_data = await ai.run("build_context", lambda: {
                "domain_mode": _infer_domain_mode_from_chunks(chunks),
                "context_str": build_epistemic_context(chunks, answer_mode, _infer_domain_mode_from_chunks(chunks))
            })
            
            domain_mode = context_data["domain_mode"]
            context_str, used_chunks = context_data["context_str"]
            
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
            
            # ... rest of the setup logic ...

            # 4. Generate Content (Tracked via LLM client or direct ai.run)
            async def _call_llm():
                return await asyncio.to_thread(
                    generate_text,
                    model=model,
                    prompt=prompt,
                    task="work_ai_answer",
                    model_tier=MODEL_TIER_FLASH,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    timeout_s=llm_timeout_s,
                    allow_pro_fallback=effective_allow_pro_fallback,
                    fallback_state=fallback_state,
                    provider_hint=provider_hint,
                    route_mode=route_mode,
                    allow_secondary_fallback=allow_secondary_fallback,
                )

            result = await ai.run("llm_generation", _call_llm)
            
            answer_text = result.text.strip()
            
            return {
                "answer": answer_text,
                "metadata": {
                    "model": result.model_used,
                    "model_tier": result.model_tier,
                    "provider_name": result.provider_name,
                    "mode": answer_mode,
                    "chunks": used_chunks,
                    "tokens": result.usage_metadata,
                    "graph_bridge_latency_ms": graph_bridge_latency_ms,
                }
            }
        except Exception as e:
            logger.error(f"[Work AI] Generation failed: {e}")
            raise e

    return await _internal_logic()


if __name__ == "__main__":
    # Simple test
    async def test():
        print("Testing Work AI...")
        # Mock data would be needed here
        pass
    
    # asyncio.run(test())
