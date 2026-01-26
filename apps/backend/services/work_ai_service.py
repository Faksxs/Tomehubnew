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
    network_status: str = "IN_NETWORK"
) -> Dict[str, Any]:
    """
    Generate an answer using the Work AI (Gemini 2.0 Flash).
    
    Args:
        question: User's question
        chunks: Retrieved and classified chunks
        answer_mode: QUOTE | SYNTHESIS | HYBRID
        confidence_score: Data quality score (0-7)
        feedback_hints: Optional hints from Judge AI for retry
        network_status: IN_NETWORK | OUT_OF_NETWORK | HYBRID
        
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
        context_str = build_epistemic_context(chunks, answer_mode)
        
        # 2. Get Base Prompt
        prompt = get_prompt_for_mode(answer_mode, context_str, question, confidence_score, network_status=network_status)
        
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
        temperature = 0.3 if answer_mode == 'QUOTE' else 0.7
        
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
                "hints_used": bool(feedback_hints)
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
