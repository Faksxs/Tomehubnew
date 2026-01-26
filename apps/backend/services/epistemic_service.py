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

# Import semantic classifier (use fast version by default for performance)
try:
    from services.semantic_classifier import classify_passage_fast as classify_passage_type
except ImportError:
    # Fallback if module not available
    def classify_passage_type(passage: str) -> Dict:
        return {'type': 'SITUATIONAL', 'quotability': 'MEDIUM', 'confidence': 0.5}

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
# Improved for Turkish agglutinative structures
DEFINITIONAL_PATTERNS_TR = [
    r'\b(\w+)\s+(nedir|ne demek|ne anlama gelir)',  # X nedir
    r'\b(\w+),?\s+.{5,50}(demektir|anlamına gelir|ifade eder)',  # X, ... demektir
    r'\b(\w+)\'?(ın|in|un|ün)\s+tanımı',  # X'in tanımı
    r'\b(\w+)\'?(ın|in|un|ün)\s+anlamı',  # X'in anlamı
    r'\b(\w+)\s+(dir|dır|dur|dür|tir|tır|tur|tür)[.,\s]',  # X ...dir.
    r'\b(\w+)\s+olarak\s+(tanımlan|değerlendiril|kabul edil)',  # X olarak tanımlanır
    r'\b(\w+)\s+(şudur|budur|odur)',  # X şudur
    r'(?:^|\.\s*)(\w+),\s+',  # "Vicdan, ..." at sentence start
    # NEW: Turkish "o da X" definitional structures
    r'o\s+da\s+(\w+)',  # "o da vicdandır"
    r'(\w+)\s+ise\s+',  # "vicdan ise..."
    r'adı\s+(\w+)',  # "adı vicdandır"
    r'özel\s+bir?\s+adı\s+var',  # "özel bir adı vardır"
]

DEFINITIONAL_PATTERNS_EN = [
    r'\b(\w+)\s+is\s+(defined|characterized|understood)\s+as',
    r'\b(\w+)\s+means\s+',
    r'\b(\w+)\s+refers\s+to',
    r'the\s+definition\s+of\s+(\w+)',
    r'\b(\w+)\s+is\s+a\s+\w+\s+(that|which)',
]

# Theory/philosophical patterns - new for better detection
THEORY_PATTERNS_TR = [
    r'iki\s+teori',  # "iki teori"
    r'iki\s+görüş',  # "iki görüş"
    r'birincisi.*ikincisi',  # "birincisi... ikincisi..."
    r'bir\s+yandan.*diğer\s+yandan',  # "bir yandan... diğer yandan..."
    r'yaklaşım\s+var',  # "yaklaşım var"
    r'teori\s+var',  # "teori var"
]

# Evaluative/judgment patterns
EVALUATIVE_PATTERNS_TR = [
    r'(değişmez|sabit|kalıcı|geçici|değişken)',  # Judgment words
    r'(olumlu|olumsuz|iyi|kötü|doğru|yanlış)',
    r'(önemli|gerekli|zorunlu|şart)',
    r'(temel|esas|asıl|birincil)',
    r'(kesinlikle|mutlaka|asla|hiçbir zaman)',
]

# Turkish suffixes for stemming
TURKISH_SUFFIXES = [
    # Verb endings (predicate suffixes)
    'dır', 'dir', 'dur', 'dür', 'tır', 'tir', 'tur', 'tür',
    # Possessive suffixes
    'ın', 'in', 'un', 'ün', 'nın', 'nin', 'nun', 'nün',
    # Accusative/dative
    'ı', 'i', 'u', 'ü', 'yı', 'yi', 'yu', 'yü',
    'a', 'e', 'ya', 'ye',
    # Locative
    'da', 'de', 'ta', 'te',
    # Ablative
    'dan', 'den', 'tan', 'ten',
    # Plural
    'lar', 'ler',
    # Adjective suffixes
    'lı', 'li', 'lu', 'lü', 'sız', 'siz', 'suz', 'süz',
]

def turkish_stem(word: str) -> str:
    """
    Simple Turkish stemmer - strips common suffixes.
    Handles agglutinative forms like vicdandır → vicdan
    """
    if not word or len(word) < 4:
        return word
        
    word_lower = word.lower()
    
    # Try to strip suffixes, longest first
    for suffix in sorted(TURKISH_SUFFIXES, key=len, reverse=True):
        if word_lower.endswith(suffix) and len(word_lower) > len(suffix) + 2:
            return word_lower[:-len(suffix)]
    
    return word_lower

# Modality/First-Person patterns (Subjectivity indicators)
MODALITY_PATTERNS_TR = [
    r'\b(bence|kanaatimce|düşünüyorum|sanırım|galiba)\b',
    r'\b(bana göre|kendi görüşüm|şahsi fikrim)\b',
    r'\b(inanıyorum|görüyorum ki|anladığım kadarıyla)\b',
    r'(?:^|\s)(?:benim|ben)\s+', # direct self-reference
]

def extract_core_concepts(question: str) -> List[str]:
    """
    Extract the core concept(s) from a user question.
    Removes stop words and generic terms.
    """
    if not question:
        return []
        
    # Normalize
    q_clean = re.sub(r'[^\w\s]', '', question.lower())
    words = q_clean.split()
    
    # Filter stopwords using the global set defined above
    keywords = [w for w in words if w not in TURKISH_STOP_WORDS and len(w) > 2]
    
    # If nothing left (e.g. "bu nedir"), take the longest word
    if not keywords and words:
        return [max(words, key=len)]
        
    return keywords

def classify_question_intent(question: str) -> tuple:
    """
    Classify the user's intent: DIRECT, COMPARATIVE, or SYNTHESIS.
    Also detects complexity for HYBRID mode.
    
    Returns:
        tuple: (intent, complexity) where complexity is 'LOW', 'MEDIUM', or 'HIGH'
    """
    q_lower = question.lower()
    
    # Complexity detection (Phase 5)
    # High complexity: philosophical, abstract, requires multiple perspectives
    complex_patterns = [
        r'değişen.*midir', r'değişir.*mi', r'sabit.*mi',  # "Is X changeable?"
        r'mümkün.*mü', r'olabilir.*mi',  # "Is X possible?"
        r'nasıl.*açıklanır', r'nasıl.*anlaşılır',  # "How is X explained?"
        r'ilişkisi.*nedir', r'bağlantısı.*ne',  # "What is the relationship?"
        r'felsef', r'ahlak', r'etik', r'vicdan',  # Philosophical keywords
        r'iki.*görüş', r'farklı.*yaklaşım',  # Multiple viewpoints
    ]
    is_complex = any(re.search(p, q_lower) for p in complex_patterns)
    complexity = 'HIGH' if is_complex else 'LOW'
    
    # Direct Definition/Fact - includes Turkish question suffixes
    direct_patterns = [
        r'nedir\??$', r'kimdir\??$', r'ne demek', r'anlamı ne', 
        r'kaç tane', r'hangi', r'nerede', r'ne zaman', r'tarih',
        r'midir\??$', r'mıdır\??$', r'mudur\??$', r'müdür\??$',  # Yes/no questions
        r'mi\??$', r'mı\??$', r'mu\??$', r'mü\??$',  # Informal yes/no
        r'mısın', r'misin', r'musun', r'müsün',  # Personal questions
    ]
    if any(re.search(p, q_lower) for p in direct_patterns):
        return ('DIRECT', complexity)
        
    # Comparative
    compare_patterns = [
        r'farkı', r'benzerliği', r'ilişkisi', r'arasındaki', 
        r'farklar', r'ortak yön', r'karşılaştır'
    ]
    if any(re.search(p, q_lower) for p in compare_patterns):
        return ('COMPARATIVE', complexity)
        
    # Synthesis (Default)
    return ('SYNTHESIS', complexity)


def calculate_answerability_score(chunk: Dict, keywords: List[str]) -> Dict:
    """
    Calculate a detailed Answerability Score (0-5) for a chunk.
    Returns dict with score and feature flags.
    """
    score = 0
    features = []
    
    text = chunk.get('content_chunk', '') or ''
    if hasattr(text, 'read'): text = text.read()
    text = str(text)
    
    personal_comment = chunk.get('personal_comment', '') or ''
    full_text = f"{text} {personal_comment}"
    
    # Feature 1: Exact/Morphological Keyword Match (+1)
    has_keyword = False
    for kw in keywords:
        if contains_keyword(full_text, kw):
            has_keyword = True
            break
            
    if has_keyword:
        score += 1
        features.append('KEYWORD_MATCH')
        
        # Feature 2: Definitional Pattern (+3, increased from +2)
        # Only check definition IF keyword is present
        is_def = False
        for kw in keywords:
            if is_definitional(full_text, kw):
                is_def = True
                break
        
        if is_def:
            score += 3  # Increased weight for definitional
            features.append('DEFINITIONAL')
        
        # Feature 2b: Theory Pattern (+1) - new
        # Detects philosophical/theoretical structures
        norm_full = normalize_for_matching(full_text)
        has_theory = any(re.search(p, norm_full, re.IGNORECASE) for p in THEORY_PATTERNS_TR)
        if has_theory:
            score += 1
            features.append('THEORY')
            
    # Feature 3: Modality / First-Person Voice (+1)
    # Check both text and personal comment
    has_modality = False
    norm_full = normalize_for_matching(full_text) if 'norm_full' not in dir() else norm_full
    for pattern in MODALITY_PATTERNS_TR:
        if re.search(pattern, norm_full, re.IGNORECASE):
            has_modality = True
            break
            
    if has_modality:
        score += 1
        features.append('MODALITY')
        
    # Feature 4: Explicit Personal Comment (+1)
    # If the user explicitly wrote a note, it's high value
    if personal_comment and len(personal_comment) > 5:
        score += 1
        features.append('PERSONAL_COMMENT')
    
    # Feature 5: Evaluative Phrases (+1) - new
    has_evaluative = any(re.search(p, norm_full, re.IGNORECASE) for p in EVALUATIVE_PATTERNS_TR)
    if has_evaluative:
        score += 1
        features.append('EVALUATIVE')
        
    return {
        'score': score,
        'features': features,
        'has_keyword': has_keyword
    }
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
    Uses simple substring matching after normalization.
    
    e.g., "vicdan" matches "vicdandır", "vicdanın", "vicdanlı" etc.
    """
    norm_text = normalize_for_matching(text)
    norm_keyword = normalize_for_matching(keyword)
    
    # Simple substring check - works perfectly for Turkish
    # Since both are normalized (lowercase, no accents), "vicdan" will match "vicdandir"
    return norm_keyword in norm_text


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
    Classify a chunk into epistemic Level A, B, or C using Answerability Score.
    Also attaches 'answerability_score' and 'epistemic_features' to the chunk.
    
    Levels:
    - Level A (Score >= 3): Definitional OR Keyword + Modality + Comment
    - Level B (Score >= 1): Has Keyword (but less weight)
    - Level C (Score 0): Conceptual only
    """
    # Calculate detailed score
    result = calculate_answerability_score(chunk, keywords)
    score = result['score']
    features = result['features']
    
    # Semantic Classification (Phase 3)
    text = chunk.get('content_chunk', '') or ''
    if hasattr(text, 'read'): text = text.read()
    semantic_result = classify_passage_type(str(text))
    
    # Attach metadata to chunk for downstream use
    chunk['answerability_score'] = score
    chunk['epistemic_features'] = features
    chunk['passage_type'] = semantic_result.get('type', 'SITUATIONAL')
    chunk['quotability'] = semantic_result.get('quotability', 'MEDIUM')
    
    # Determine Level based on Score, Features, AND Semantic Type
    # Level A: High score OR definitional/theory feature OR DEFINITION/THEORY type
    is_priority = (
        score >= 3 or 
        'DEFINITIONAL' in features or 
        'THEORY' in features or
        semantic_result.get('type') in ['DEFINITION', 'THEORY'] or
        semantic_result.get('quotability') == 'HIGH'
    )
    
    if is_priority:
        level = 'A'
    elif score >= 1:
        level = 'B'
    else:
        level = 'C'
    
    # CRITICAL: Store the level on the chunk (was missing!)
    chunk['epistemic_level'] = level
        
    return level


def determine_answer_mode(classified_chunks: List[Dict], question_intent: str = 'SYNTHESIS', complexity: str = 'LOW') -> str:
    """
    Determine whether to use QUOTE, SYNTHESIS, or HYBRID mode based on 
    Answerability Scores, Question Intent, and Complexity.
    
    Gateway Logic (Phase 5: HYBRID Mode):
    1. If Direct question AND HIGH complexity -> HYBRID (Quote opposing views + Synthesize)
    2. If Direct question AND LOW complexity + definitional evidence -> QUOTE
    3. If Comparative question AND strong evidence -> QUOTE
    4. If multiple keyword matches -> QUOTE
    5. Fallback -> SYNTHESIS
    """
    # Analyze features across all chunks
    has_definitional = any('DEFINITIONAL' in c.get('epistemic_features', []) for c in classified_chunks)
    has_theory = any('THEORY' in c.get('epistemic_features', []) for c in classified_chunks)
    
    # Score-based counts
    high_confidence_count = sum(1 for c in classified_chunks if c.get('answerability_score', 0) >= 2)
    evidence_count = sum(1 for c in classified_chunks if c.get('answerability_score', 0) >= 1)
    
    # Phase 12: Soft Valid Gate
    # Capture high-quality notes (Score >= 3) that might miss strict Definition tag
    has_high_score_evidence = any(c.get('answerability_score', 0) >= 3 for c in classified_chunks)
    
    # GATE 0: HYBRID Mode (Phase 5)
    # For complex philosophical questions that are DIRECT in form but need both quote AND synthesis
    # RELAXED: Now also triggers if we just have decent evidence (evidence_count >= 2)
    if question_intent == 'DIRECT' and complexity == 'HIGH' and (has_definitional or has_theory or evidence_count >= 2):
        return 'HYBRID'
    
    # GATE 1: DIRECT Question + Definitional/Theory OR High Score Evidence
    # For simple "nedir" questions, allow QUOTE mode if we have strong evidence
    if question_intent == 'DIRECT' and (has_definitional or has_theory or has_high_score_evidence):
        return 'QUOTE'
    
    # GATE 2: DIRECT/COMPARATIVE Question + Any decent evidence (Score >= 2)
    if question_intent in ['DIRECT', 'COMPARATIVE'] and high_confidence_count >= 1:
        return 'QUOTE'
        
    # GATE 3: Any Question + Multiple keyword matches
    # If we have 3+ chunks with the keyword, we should quote them
    if evidence_count >= 3:
        return 'QUOTE'
        
    # GATE 4: Fallback
    return 'SYNTHESIS'








def build_epistemic_context(chunks: List[Dict], answer_mode: str) -> str:
    """
    Build context string with epistemic priority markers AND metadata.
    Includes Answerability Score and Features for the LLM.
    """
    context_parts = []
    
    # Sort by Answerability Score (High to Low)
    sorted_chunks = sorted(chunks, key=lambda c: c.get('answerability_score', 0), reverse=True)
    
    # LIMIT CONTEXT: Only use top 12 chunks to prevent overwhelming the LLM and "list mania"
    sorted_chunks = sorted_chunks[:12]
    
    for i, chunk in enumerate(sorted_chunks, 1):
        level = chunk.get('epistemic_level', 'C')
        score = chunk.get('answerability_score', 0)
        features = chunk.get('epistemic_features', [])
        
        # Phase 3: Semantic type and quotability
        passage_type = chunk.get('passage_type', 'SITUATIONAL')
        quotability = chunk.get('quotability', 'MEDIUM')
        
        # Determine strict match boolean for LLM prompt
        exact_match = 'KEYWORD_MATCH' in features
        
        title = chunk.get('title', 'Unknown')
        text = chunk.get('content_chunk', '')
        if hasattr(text, 'read'):
            text = text.read()
        text = str(text)[:500]
        
        personal_comment = chunk.get('personal_comment', '')
        summary = chunk.get('summary', '')
        
        # Phase 4: Enhanced Metadata Header with Type/Quotability
        # LLM uses this to decide what to quote vs synthesize
        meta_header = f"[ID: {i} | Score: {score}/7 | Level: {level} | Type: {passage_type} | Quotability: {quotability} | ExactMatch: {exact_match}]"
        
        # Priority marker based on quotability
        if quotability == 'HIGH' or level == 'A':
            marker = "★★★ DOĞRUDAN ALINTI YAP (Quote Verbatim)"
        elif level == 'B':
            marker = "★★ BAĞLAMDA KULLAN (Use in Context)"
        else:
            marker = "★ SENTEZ YAP (Synthesize Only)"
        
        block = f"{meta_header}\n{marker} Kaynak: {title}\n"
        
        if text:
            block += f"- ALINTI: {text}\n"
        if personal_comment:
            block += f"- KİŞİSEL NOT: {personal_comment}\n"
        if summary:
            block += f"- ÖZET: {summary}\n"
        
        block += "---\n"
        context_parts.append(block)
    
    return "\n".join(context_parts)



def get_prompt_for_mode(answer_mode: str, context: str, question: str, confidence_score: float = 5.0, network_status: str = "IN_NETWORK") -> str:
    """
    Get the appropriate prompt based on answer mode, confidence, and network coverage.
    """
    # 1. Determine Style based on Confidence
    if confidence_score >= 4.0:
        style_instruction = "STİL: ÇÖZÜMLEYİCİ ve AKICI (Narrative Mode). Konuyu derinlemesine anlat, bağlaçlar kullan."
    else:
        style_instruction = "STİL: ÖZETLEYİCİ ve TEMKİNLİ (Concise Mode). Veri az olduğu için kısa ve net yaz. Yorum katma."

    # 2. Network Grounding Instruction (Phase 3)
    if network_status == "IN_NETWORK":
        grounding_rule = "KURAL: SADECE sana verilen 'BAĞLAM' içerisindeki bilgileri kullan. Kendi dış bilgini ASLA ekleme. Eğer bağlamda cevap yoksa 'Bilgi bulunamadı' de ve uydurma."
    elif network_status == "OUT_OF_NETWORK":
        grounding_rule = "UYARI: Kullanıcının notlarında bu konuda yeterli bilgi BULUNAMADI. Genel bilgini kullanarak cevaplayabilirsin ANCAK cevabın başında 'Notlarınızda bu konuda yeterli bilgi bulamadım, genel bilgilere dayanarak cevaplıyorum:' ibaresini MUTLAKA kullan."
    else: # HYBRID
        grounding_rule = "TALİMAT: Öncelikle verilen bağlamı temel al. Ancak bağlamdaki boşlukları doldurmak, terimleri açıklamak veya akıcılığı sağlamak için genel bilgini KISITLI olarak kullanabilirsin."

    intro = f"""Sen bir düşünce ortağısın (thought partner) ve kullanıcının kişisel notlarını analiz ediyorsun.

{grounding_rule}
{style_instruction}"""

    if answer_mode == 'QUOTE':
        return f"""{intro}

ÖNEMLİ: Bu soruda YÜKSEK GÜVENİLİRLİKLİ notlar bulundu.

İKİ AŞAMALI YANITLAMA SÜRECİ (+ İÇ KONTROL):

## AŞAMA 0: MİKRO İÇ KONTROL (Silent Self-Review)
Cevabı yazmadan önce zihninde şunları kontrol et:
1. Seçilen metinde OCR hatası (örn: "dagas1") var mı? Varsa düzelt.
2. Tam olarak 3 adet tanım seçtin mi?
3. Kaynaklar doğru mu?

## AŞAMA 1: DOĞRUDAN ALINTI (Quote Section)
Quotability=HIGH veya Type=DEFINITION/THEORY olan notlardan KELİMESİ KELİMESİNE alıntı yap, ANCAK:

1. **OCR HATALARINI DÜZELT:** Metindeki bozuk karakterleri (örn: "dagas1" -> "doğası", "c;:ah~an" -> "çalışan") düzgün Türkçe ile yaz.
2. **SADECE EN İYİ 3 TANIMI SEÇ:** Listeyi uzatma. En alakalı ve net 3 tanımı al.
3. Kaynak belirt: [Kaynak: Kitap Adı]

## AŞAMA 2: GENİŞ KAPSAMLI BAĞLAMSAL ANALİZ (Synthesis Section)  
Quotability=MEDIUM/LOW olan notlardan sentez yap:
1. "Bağlamsal açıdan incelendiğinde..." diyerek başla.
2. Sadece notları özetleme; notlar arasındaki İLİŞKİLERİ, ZAMAN farklarını ve ORTAK TEMALARI analiz et.
3. Konuyu (örn: vicdan, ahlak) bireysel, toplumsal ve evrensel boyutlarıyla ele al.
4. Varsa notlardaki çelişkileri veya gelişim sürecini vurgula.

BAĞLAM (Metadata + Content):
{context}

KULLANICI SORUSU:
{question}

ZORUNLU ÇIKTI FORMATI (Bu başlıkları kullan):

## Doğrudan Tanımlar
[Buraya Quotability=HIGH notlardan verbatim alıntılar]

## Bağlamsal Analiz
[Buraya geniş kapsamlı ve çok boyutlu sentez]

## Sonuç
[Kısa özet]

CEVAP:"""
    
    elif answer_mode == 'HYBRID':
        # Phase 5: HYBRID mode for complex philosophical questions
        return f"""{intro}

ÖNEMLİ: Bu KARMAŞIK bir felsefi soru. Hem teorik tanımlar hem de bağlamsal örnekler gerekli.

HİBRİT MOD - ÇİFT AŞAMALI ANALİZ:

## AŞAMA 1: KARŞIT GÖRÜŞLER (Quote Opposing Views)
Bu konuda farklı teorik yaklaşımlar var. Her birini AYRI AYRI belirt:
1. "İlk görüşe göre..." - Type=THEORY veya Type=DEFINITION notlardan alıntı
2. "İkinci görüşe göre..." - Karşıt tanım/teoriyi alıntıla

## AŞAMA 2: GENİŞ BAĞLAMSAL KANITLAR (Contextual Evidence)
Quotability=MEDIUM notlardan durumsal ve toplumsal örnekler sentezle:
1. "Kişisel ve toplumsal bağlamda..." diyerek analizi genişlet.
2. Kavramın farklı durumlarda nasıl değiştiğini veya korunduğunu irdele.
3. Sadece örnek verme; bu örneklerin arkasındaki BÜYÜK RESMİ (Big Picture) anlat.

## AŞAMA 3: DENGELİ SONUÇ (Balanced Conclusion)
Her iki görüşü de dikkate alarak dengeli bir sonuç sun.

BAĞLAM (Metadata + Content):
{context}

KULLANICI SORUSU:
{question}

ZORUNLU ÇIKTI FORMATI:

## Karşıt Görüşler
**Birinci Görüş:** "[AYNEN ALINTI]" [Kaynak: X]
**İkinci Görüş:** "[AYNEN ALINTI]" [Kaynak: Y]

## Bağlamsal Kanıtlar
[Durumsal, toplumsal ve geniş perspektifli sentez]

## Sonuç
[Dengeli, her iki görüşü kapsayan yorum]

CEVAP:"""
    
    else:  # SYNTHESIS mode
        return f"""{intro}

DURUM: Sentez ve yorumlama modu aktif.
(Doğrudan tanım bulunamamış olabilir ancak bağlamsal kanıtlar mevcut.)

TALİMATLAR:
1. Mevcut notları birleştirerek çıkarım yap
2. "Notlarından çıkarıma göre..." ile başla
3. Kesin hüküm verme, belirsizliği ifade et
4. Kaynak göster ama doğrudan alıntı yapma
5. TÜRKÇE cevap ver

BAĞLAM (Metadata + Content):
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
