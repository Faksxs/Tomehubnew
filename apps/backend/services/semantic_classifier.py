"""
Semantic Classifier Service
============================
Uses Gemini Flash for fast semantic classification of passages.

Classifies passages into:
- Type: DEFINITION, THEORY, ANALOGY, SITUATIONAL, SOCIETAL
- Quotability: HIGH (quote verbatim), MEDIUM (can quote), LOW (synthesize only)
"""

import os
import re
import json
import google.generativeai as genai
from typing import Dict, Optional
from functools import lru_cache

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Use Flash for speed
CLASSIFIER_MODEL = genai.GenerativeModel('gemini-2.0-flash')

# Classification prompt template
CLASSIFICATION_PROMPT = """Aşağıdaki Türkçe metin parçasını analiz et ve JSON formatında sınıflandır.

METİN:
"{passage}"

SINIFLANDIRMA KRİTERİLERİ:

1. TYPE (Metin Tipi):
- DEFINITION: Bir kavramın tanımını içerir ("X nedir", "X şudur", "o da X")
- THEORY: Felsefi teori veya görüş sunar ("iki teori var", "yaklaşıma göre")
- ANALOGY: Benzetme veya metafor kullanır ("X gibi Y", "tıpkı X")
- SITUATIONAL: Kişisel deneyim veya durum anlatır ("bir gün", "yaşadım")
- SOCIETAL: Toplumsal/kültürel yorum içerir ("toplumda", "genel olarak")

2. QUOTABILITY (Alıntılanabilirlik):
- HIGH: Doğrudan alıntı yapılmalı (tanım, teori, önemli görüş)
- MEDIUM: Alıntı yapılabilir (destekleyici kanıt)
- LOW: Sadece sentezde kullanılmalı (bağlamsal bilgi)

SADECE aşağıdaki JSON formatında yanıt ver, başka açıklama ekleme:
{{"type": "DEFINITION|THEORY|ANALOGY|SITUATIONAL|SOCIETAL", "quotability": "HIGH|MEDIUM|LOW", "confidence": 0.0-1.0}}
"""

# Cache for performance (avoid re-classifying same passages)
@lru_cache(maxsize=500)
def _cached_classify(passage_hash: str, passage_preview: str) -> Dict:
    """
    Internal cached classification.
    Uses hash + preview for cache key since full passage may be too long.
    """
    return _call_gemini_classifier(passage_preview)


def _call_gemini_classifier(passage: str) -> Dict:
    """
    Call Gemini Flash for classification.
    Returns dict with type, quotability, confidence.
    """
    try:
        # Truncate very long passages
        passage_truncated = passage[:1000] if len(passage) > 1000 else passage
        
        prompt = CLASSIFICATION_PROMPT.format(passage=passage_truncated)
        
        # Task 2.4: Add timeout
        response = CLASSIFIER_MODEL.generate_content(
            prompt,
            request_options={'timeout': 20},
            generation_config={
                'temperature': 0.1,  # Low temperature for consistent classification
                'max_output_tokens': 100
            }
        )
        
        # Parse JSON response
        text = response.text.strip()
        
        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{[^}]+\}', text)
        if json_match:
            result = json.loads(json_match.group())
            return {
                'type': result.get('type', 'SITUATIONAL'),
                'quotability': result.get('quotability', 'MEDIUM'),
                'confidence': float(result.get('confidence', 0.7))
            }
        else:
            # Fallback if JSON parsing fails
            return {'type': 'SITUATIONAL', 'quotability': 'MEDIUM', 'confidence': 0.5}
            
    except Exception as e:
        print(f"[SEMANTIC_CLASSIFIER] Error: {e}")
        return {'type': 'SITUATIONAL', 'quotability': 'MEDIUM', 'confidence': 0.0}


def classify_passage_type(passage: str, use_cache: bool = True) -> Dict:
    """
    Classify a passage into semantic types using Gemini.
    
    Args:
        passage: The text to classify
        use_cache: Whether to use LRU cache (default True)
    
    Returns:
        {
            'type': 'DEFINITION' | 'THEORY' | 'ANALOGY' | 'SITUATIONAL' | 'SOCIETAL',
            'quotability': 'HIGH' | 'MEDIUM' | 'LOW',
            'confidence': 0.0-1.0
        }
    """
    if not passage or len(passage) < 20:
        return {'type': 'SITUATIONAL', 'quotability': 'LOW', 'confidence': 0.0}
    
    if use_cache:
        # Use hash + first 100 chars as cache key
        passage_hash = str(hash(passage))
        passage_preview = passage[:100]
        return _cached_classify(passage_hash, passage_preview)
    else:
        return _call_gemini_classifier(passage)


def batch_classify_passages(passages: list, max_concurrent: int = 5) -> list:
    """
    Classify multiple passages (for batch operations).
    
    Note: Currently sequential for simplicity. 
    Could be parallelized with asyncio if needed.
    """
    results = []
    for passage in passages:
        result = classify_passage_type(passage)
        results.append(result)
    return results


# Quick rule-based fallback (faster, no API call)
def classify_passage_fast(passage: str) -> Dict:
    """
    Fast rule-based classification without API call.
    Use as fallback or for high-volume cases.
    """
    passage_lower = passage.lower()
    
    # Check for definitional patterns
    definitional_patterns = [
        r'\bnedir\b', r'\bşudur\b', r'\bdemektir\b', r'\bo da\s+\w+',
        r'\btanımı\b', r'\banlamı\b', r'olarak tanımlan'
    ]
    for pattern in definitional_patterns:
        if re.search(pattern, passage_lower):
            return {'type': 'DEFINITION', 'quotability': 'HIGH', 'confidence': 0.8}
    
    # Check for theory patterns
    theory_patterns = [
        r'iki\s+teori', r'iki\s+görüş', r'yaklaşım\w*\s+var',
        r'birincisi.*ikincisi', r'felsefi\s+olarak'
    ]
    for pattern in theory_patterns:
        if re.search(pattern, passage_lower):
            return {'type': 'THEORY', 'quotability': 'HIGH', 'confidence': 0.8}
    
    # Check for analogy
    analogy_patterns = [r'\bgibi\b', r'tıpkı', r'benzer\s+şekilde', r'sanki']
    for pattern in analogy_patterns:
        if re.search(pattern, passage_lower):
            return {'type': 'ANALOGY', 'quotability': 'MEDIUM', 'confidence': 0.7}
    
    # Check for situational
    situational_patterns = [r'yaşadım', r'gördüm', r'bir gün', r'hatırlıyorum']
    for pattern in situational_patterns:
        if re.search(pattern, passage_lower):
            return {'type': 'SITUATIONAL', 'quotability': 'MEDIUM', 'confidence': 0.7}
    
    # Check for societal
    societal_patterns = [r'toplum\w*', r'kültür\w*', r'genel\s+olarak', r'insanlar']
    for pattern in societal_patterns:
        if re.search(pattern, passage_lower):
            return {'type': 'SOCIETAL', 'quotability': 'MEDIUM', 'confidence': 0.7}
    
    # Default fallback
    return {'type': 'SITUATIONAL', 'quotability': 'MEDIUM', 'confidence': 0.5}


# Module test
if __name__ == "__main__":
    test_passages = [
        "İyiyi kötüden ayırma yeteneğinin özel bir adı vardır, o da vicdandır.",
        "Vicdan için iki teori vardır: birincisi sosyal kanunlarla karıştıran, ikincisi değişmez bir kanun olarak gören.",
        "Ayrılmak ne tuhaf kalan daha çok ızdırap çektiği için giden biraz vicdan azabı duyar.",
        "Toplumda vicdan kavramı farklı şekillerde yorumlanmaktadır.",
    ]
    
    print("Testing Semantic Classifier...")
    for passage in test_passages:
        result = classify_passage_fast(passage)  # Use fast version for testing
        print(f"\nPassage: {passage[:50]}...")
        print(f"Result: {result}")
