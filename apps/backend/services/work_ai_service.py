# -*- coding: utf-8 -*-
import os
import json
import asyncio
import logging
from typing import List, Optional, Dict, Any
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

from services.epistemic_service import get_prompt_for_mode, build_epistemic_context

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

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
    conversation_state: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate an answer using the Work AI (Gemini 2.0 Flash).
    
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
                "model": "gemini-2.0-flash",
                "mode": answer_mode,
                "hints_used": bool
            }
        }
    """
    try:
        # 1. Build Context
        context_str, used_chunks = build_epistemic_context(chunks, answer_mode)
        
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
        #         "model": "gemini-2.0-flash",
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
        model = genai.GenerativeModel('gemini-2.0-flash')
        
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
        
        response = await asyncio.to_thread(
            model.generate_content, 
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=2048,
            )
        )
        
        answer_text = response.text.strip()
        
        return {
            "answer": answer_text,
            "metadata": {
                "model": "gemini-2.0-flash",
                "mode": answer_mode,
                "temperature": temperature,
                "hints_used": bool(feedback_hints),
                "chunks": used_chunks
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
