# -*- coding: utf-8 -*-
"""
TomeHub Correction Service
==========================
Handles automated text repair for low-confidence OCR results using Gemini LLM.

Author: TomeHub Team
Date: 2026-01-15
"""

import os
from typing import Optional
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(dotenv_path=env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def repair_ocr_text(text: str) -> str:
    """
    Reconstructs original text from corrupted OCR output using Gemini.
    
    Args:
        text (str): Corrupted text from OCR
        
    Returns:
        str: Repaired text, or original text if repair fails
    """
    if not text or len(text.strip()) < 10:
        return text

    if not GEMINI_API_KEY:
        return text

    prompt = f"""
    The following text was extracted via OCR and contains errors, typos, and artifacts (e.g., 'Philo5ophy' instead of 'Philosophy'). 
    Please reconstruct the original text based on context, fixing typos and artifacts while preserving the semantic meaning exactly. 
    Do not add any comments or headers. Return ONLY the repaired text.

    CORRUPTED TEXT:
    ---
    {text}
    ---
    
    REPAIRED TEXT:
    """

    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        # Task 2.4: Add timeout
        response = model.generate_content(prompt, request_options={'timeout': 30})
        
        if response and response.text:
            repaired_text = response.text.strip()
            # If Gemini returns an empty or obviously too short response, fallback
            if len(repaired_text) < len(text) * 0.5:
                return text
            return repaired_text
        
        return text
    except Exception as e:
        # Silently fail and return original text during ingestion
        return text
