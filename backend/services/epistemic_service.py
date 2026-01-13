"""
Epistemic Control Layer Service
================================
Implements the Epistemic Hierarchy for Layer-3 answer generation.

Level A: Exact keyword + definitional/evaluative statement (HIGHEST PRIORITY)
Level B: Exact keyword but contextual reference only (MEDIUM)
Level C: Conceptual match, no exact keyword (LOWEST)

This service fixes the "Epistemic Underspecification" failure class where the AI
fails to recognize that retrieved information constitutes a direct answer.
"""

import re
from typing import List, Dict, Tuple, Optional

# Turkish stop words to filter out from keyword extraction
TURKISH_STOP_WORDS = {
    've', 'veya', 'ile', 'ama', 'fakat', 'ancak', 'lakin', 'ki', 'de', 'da',
    'mi', 'mu', 'mı', 'mü', 'bir', 'bu', 'şu', 'o', 'ben', 'sen', 'biz',
    'siz', 'onlar', 'gibi', 'için', 'diye', 'en', 'daha', 'çok', 'her',
    'hangi', 'ne', 'kim', 'bunu', 'şunu', 'böyle', 'şöyle', 'nasıl',
    'neden', 'niçin', 'niye', 'kadar', 'arasında', 'üzerinde', 'altında',
    'içinde', 'dışında', 'önce', 'sonra', 'şey', 'şeyi', 'şeyin', 'olan',
    'olarak', 'olduğu', 'olduğunu', 'değil', 'var', 'yok', 'ise', 'eğer',
    'bile', 'sadece', 'yalnızca', 'hep', 'hiç', 'artık', 'henüz', 'zaten'
}

# Definitional/evaluative patterns that indicate Level A
DEFINITIONAL_PATTERNS_TR = [
    r'\b(\w+)\s+(nedir|ne demek|ne anlama gelir)',  # X nedir
    r'\b(\w+),?\s+.{5,50}(demektir|anlamına gelir|ifade eder)',  # X, ... demektir
    r'\b(\w+)\'?(ın|in|un|ün)\s+tanımı',  # X'in tanımı
    r'\b(\w+)\'?(ın|in|un|ün)\s+anlamı',  # X'in anlamı
    r'\b(\w+)\s+(dir|dır|dur|dür|tir|tır|tur|tür)[.,\s]',  # X ...dir.
    r'\b(\w+)\s+olarak\s+(tanımlan|değerlendiril|kabul edil)',  # X olarak tanımlanır
    r'\b(\w+)\s+(şudur|budur|odur)',  # X şudur
    r'(?:^|\.\s*)(\w+),\s+',  # "Vicdan, ..." at sentence start
]

DEFINITIONAL_PATTERNS_EN = [
    r'\b(\w+)\s+is\s+(defined|characterized|understood)\s+as',
    r'\b(\w+)\s+means\s+',
    r'\b(\w+)\s+refers\s+to',
    r'the\s+definition\s+of\s+(\w+)',
    r'\b(\w+)\s+is\s+a\s+\w+\s+(that|which)',
]

# Evaluative/judgment patterns
EVALUATIVE_PATTERNS_TR = [
    r'(değişmez|sabit|kalıcı|geçici|değişken)',  # Judgment words
    r'(olumlu|olumsuz|iyi|kötü|doğru|yanlış)',
    r'(önemli|gerekli|zorunlu|şart)',
    r'(temel|esas|asıl|birincil)',
    r'(kesinlikle|mutlaka|asla|hiçbir zaman)',
]


def extract_core_concepts(question: str) -> List[str]:
    """
    Extract the core concept(s) from a user question.
    
    Args:
        question: The user's question string
        
    Returns:
        List of core concept keywords (lowercase, deaccented)
    """
    # Normalize
    q_lower = question.lower().strip()
    
    # Remove question marks and common question words
    q_clean = re.sub(r'[?!.,;:\'"()]', '', q_lower)
    
    # Tokenize
    tokens = q_clean.split()
    
    # Filter stop words
    keywords = [t for t in tokens if t not in TURKISH_STOP_WORDS and len(t) > 2]
    
    # If we filtered too much, take the longest remaining word
    if not keywords and tokens:
        keywords = [max(tokens, key=len)]
    
    return keywords


def normalize_for_matching(text: str) -> str:
    """Normalize text for keyword matching (lowercase, remove accents)."""
    if not text:
        return ""
    
    text = text.lower()
    
    # Turkish character normalization
    replacements = {
        'ı': 'i', 'ğ': 'g', 'ü': 'u', 'ş': 's', 'ö': 'o', 'ç': 'c',
        'İ': 'i', 'Ğ': 'g', 'Ü': 'u', 'Ş': 's', 'Ö': 'o', 'Ç': 'c'
    }
    for tr_char, en_char in replacements.items():
        text = text.replace(tr_char, en_char)
    
    return text


def contains_keyword(text: str, keyword: str) -> bool:
    """
    Check if text contains the keyword (case-insensitive, accent-normalized).
    Uses prefix matching for Turkish agglutinative morphology.
    e.g., "vicdan" matches "vicdani", "vicdanın", "vicdanlı" etc.
    """
    norm_text = normalize_for_matching(text)
    norm_keyword = normalize_for_matching(keyword)
    
    # For Turkish: Use prefix-based matching (keyword as word start)
    # This handles suffixed forms: vicdan → vicdani, vicdanın, vicdanı
    # Pattern: word boundary before keyword, then keyword, then optional word chars
    pattern = r'\b' + re.escape(norm_keyword) + r'\w*'
    return bool(re.search(pattern, norm_text))


def is_definitional(text: str, keyword: str) -> bool:
    """
    Check if the text provides a definitional or evaluative statement about the keyword.
    
    This indicates Level A - the highest epistemic priority.
    """
    norm_text = normalize_for_matching(text)
    norm_keyword = normalize_for_matching(keyword)
    
    # Check Turkish definitional patterns
    for pattern in DEFINITIONAL_PATTERNS_TR:
        # Replace placeholder with actual keyword
        specific_pattern = pattern.replace(r'(\w+)', re.escape(norm_keyword))
        if re.search(specific_pattern, norm_text, re.IGNORECASE):
            return True
    
    # Check English definitional patterns
    for pattern in DEFINITIONAL_PATTERNS_EN:
        specific_pattern = pattern.replace(r'(\w+)', re.escape(norm_keyword))
        if re.search(specific_pattern, norm_text, re.IGNORECASE):
            return True
    
    # Check if keyword appears near evaluative words (within 50 chars)
    keyword_pos = norm_text.find(norm_keyword)
    if keyword_pos >= 0:
        context_window = norm_text[max(0, keyword_pos-50):keyword_pos+len(norm_keyword)+50]
        for pattern in EVALUATIVE_PATTERNS_TR:
            if re.search(pattern, context_window, re.IGNORECASE):
                return True
    
    # Check sentence structure: "Keyword, ..." at start of sentence
    sentences = re.split(r'[.!?]\s+', text)
    for sentence in sentences:
        norm_sentence = normalize_for_matching(sentence.strip())
        if norm_sentence.startswith(norm_keyword + ',') or norm_sentence.startswith(norm_keyword + ' '):
            # Sentence starts with keyword - likely definitional
            if len(sentence) > len(keyword) + 10:  # Has substantial content
                return True
    
    return False


def classify_chunk(keywords: List[str], chunk: Dict) -> str:
    """
    Classify a chunk into epistemic Level A, B, or C.
    
    Args:
        keywords: Core concepts extracted from the question
        chunk: Retrieved chunk with 'content_chunk', 'title', etc.
        
    Returns:
        'A' (definitional), 'B' (contextual), or 'C' (conceptual only)
    """
    # Get text content from chunk
    text = chunk.get('content_chunk', '') or ''
    if hasattr(text, 'read'):
        text = text.read()
    text = str(text)
    
    # Also check personal comment if available
    personal_comment = chunk.get('personal_comment', '') or ''
    full_text = f"{text} {personal_comment}"
    
    # Check each keyword
    for keyword in keywords:
        if contains_keyword(full_text, keyword):
            # Found keyword - check if definitional
            if is_definitional(full_text, keyword):
                return 'A'  # Definitional/evaluative
            else:
                return 'B'  # Contextual only
    
    # No exact keyword match
    return 'C'  # Conceptual/related


def determine_answer_mode(classified_chunks: List[Dict]) -> str:
    """
    Determine whether to use QUOTE mode or SYNTHESIS mode.
    
    QUOTE mode = Direct evidence exists, cite the notes
    SYNTHESIS mode = No direct evidence, infer from context
    
    Args:
        classified_chunks: List of chunks with 'epistemic_level' field
        
    Returns:
        'QUOTE' if direct keyword matches exist, 'SYNTHESIS' otherwise
    """
    level_a_count = sum(1 for c in classified_chunks if c.get('epistemic_level') == 'A')
    level_b_count = sum(1 for c in classified_chunks if c.get('epistemic_level') == 'B')
    
    # QUOTE MODE triggers:
    # 1. Any Level A (definitional) chunk exists
    if level_a_count >= 1:
        return 'QUOTE'
    
    # 2. Multiple Level B (contextual keyword) chunks exist
    #    This means the user has notes that directly mention the concept
    if level_b_count >= 2:
        return 'QUOTE'
    
    # Fallthrough: No direct keyword matches
    return 'SYNTHESIS'


def build_epistemic_context(chunks: List[Dict], answer_mode: str) -> str:
    """
    Build context string with epistemic priority markers.
    
    Args:
        chunks: Classified chunks with 'epistemic_level'
        answer_mode: 'QUOTE' or 'SYNTHESIS'
        
    Returns:
        Formatted context string with priority markers
    """
    context_parts = []
    
    # Sort by epistemic level (A first, then B, then C)
    level_priority = {'A': 0, 'B': 1, 'C': 2}
    sorted_chunks = sorted(chunks, key=lambda c: level_priority.get(c.get('epistemic_level', 'C'), 2))
    
    for i, chunk in enumerate(sorted_chunks, 1):
        level = chunk.get('epistemic_level', 'C')
        title = chunk.get('title', 'Unknown')
        text = chunk.get('content_chunk', '')
        if hasattr(text, 'read'):
            text = text.read()
        text = str(text)[:500]  # Truncate for context window
        
        personal_comment = chunk.get('personal_comment', '')
        summary = chunk.get('summary', '')
        
        # Priority marker based on level
        if level == 'A':
            marker = "★★★ DOĞRUDAN CEVAP - Level A"
        elif level == 'B':
            marker = "★★ İLGİLİ - Level B"
        else:
            marker = "★ KAVRAMSAL - Level C"
        
        block = f"[{marker}] Kaynak {i}: {title}\n"
        
        if text:
            block += f"- ALINTI (Highlight): {text}\n"
        if personal_comment:
            block += f"- KİŞİSEL NOT: {personal_comment}\n"
        if summary:
            block += f"- ÖZET: {summary}\n"
        
        block += "---\n"
        context_parts.append(block)
    
    return "\n".join(context_parts)


def get_prompt_for_mode(answer_mode: str, context: str, question: str) -> str:
    """
    Get the appropriate prompt based on answer mode.
    
    Args:
        answer_mode: 'QUOTE' or 'SYNTHESIS'
        context: Epistemic-labeled context string
        question: The user's question
        
    Returns:
        Complete prompt for Gemini
    """
    if answer_mode == 'QUOTE':
        return f"""Sen bir düşünce ortağısın (thought partner) ve kullanıcının kişisel notlarını analiz ediyorsun.

ÖNEMLİ: Bu soruda ilgili notlar bulundu. Aşağıdaki kaynakları kullanarak cevap ver.

EPİSTEMİK HİYERARŞİ:
★★★ Level A = Doğrudan tanım/değerlendirme - ÖNCE bunlardan alıntı yap
★★ Level B = Anahtar kelimeyi içeren notlar - Level A yoksa BUNLARI kullan
★ Level C = Kavramsal ilişki - Sadece destekleyici

TALİMATLAR:
1. Eğer Level A kaynaklar varsa, ÖNCE onlardan alıntı yap
2. Level A yoksa, Level B kaynaklardan alıntı yap - bunlar anahtar kelimeyi doğrudan içeriyor
3. "Notlarında belirttiğin gibi..." veya "X kitabında yazdığın..." gibi ifadeler kullan
4. Alıntıları VE kaynak adlarını belirt
5. TÜRKÇE cevap ver
6. Sentez yaparken bile önce alıntılarla başla

BAĞLAM (EPİSTEMİK SEVİYELİ):
{context}

KULLANICI SORUSU:
{question}

CEVAP (Önce Level A/B alıntı, sonra yorum):"""
    
    else:  # SYNTHESIS mode
        return f"""Sen bir düşünce ortağısın (thought partner) ve kullanıcının kişisel notlarını analiz ediyorsun.

NOT: Bu soruda doğrudan bir tanım/değerlendirme bulunamadı. Sentez modunda çalışıyorsun.

TALİMATLAR:
1. Farklı notları birbirine bağlayarak sentez yap
2. "Notlarından çıkarıma göre..." gibi ifadeler kullan - bunun bir YORUM olduğunu belirt
3. Semantic köprüleri (graph bridges) kullanarak bağlantı kur
4. Emin olamadığın yerlerde "kesin söyleyemiyorum ama..." de
5. TÜRKÇE cevap ver
6. Eğer notlarda hiç bilgi yoksa: "Notlarında bu konuda bir bilgi bulamadım" de

BAĞLAM:
{context}

KULLANICI SORUSU:
{question}

CEVAP (Sentez ve çıkarım):"""


# ============================================================================
# TEST BLOCK
# ============================================================================

if __name__ == "__main__":
    print("=== Epistemic Service Test ===\n")
    
    # Test keyword extraction
    test_q = "vicdan değişen bir şey midir"
    keywords = extract_core_concepts(test_q)
    print(f"Question: {test_q}")
    print(f"Keywords: {keywords}\n")
    
    # Test classification
    test_chunks = [
        {"content_chunk": "Vicdan, insanın içindeki değişmez bir ölçüdür.", "title": "Ahlak Notları"},
        {"content_chunk": "Bu kitapta vicdanın rolü tartışılıyor.", "title": "Felsefe"},
        {"content_chunk": "Etik değerler toplumdan topluma farklılık gösterir.", "title": "Sosyoloji"},
    ]
    
    for chunk in test_chunks:
        level = classify_chunk(keywords, chunk)
        print(f"Level {level}: {chunk['title']} - {chunk['content_chunk'][:50]}...")
    
    print("\n=== Test Complete ===")
