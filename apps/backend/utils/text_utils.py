
import unicodedata
import re

def normalize_text(text: str) -> str:
    """
    Two-Way Normalization for Turkish Search.
    
    1. Lowercase with Turkish awareness (I -> ı, İ -> i)
    2. ASCII transliteration (ş -> s, ç -> c, ğ -> g, etc.)
    3. Punctuation removal
    4. Collapse whitespace
    
    Example:
        "Yanılsamalar" -> "yanilsamalar"
        "ÇIPLAKLIK" -> "ciplaklik"
    """
    if not text:
        return ""
    
    # 0. Unicode Normalization (Handle composed chars like ü = u + ¨)
    text = unicodedata.normalize('NFC', text)
    
    # 1. Turkish Lowercase Mapping
    # Standard .lower() maps 'I' -> 'i' which is wrong for Turkish.
    # We must explicitly handle I -> ı and İ -> i
    text = text.replace('İ', 'i').replace('I', 'ı')
    text = text.lower()
    
    # 2. Transliteration (Turkish characters to ASCII equivalents)
    replacements = {
        'ı': 'i',
        'ş': 's',
        'ç': 'c',
        'ğ': 'g',
        'ü': 'u',
        'ö': 'o',
        'â': 'a',
        'î': 'i',
        'û': 'u'
    }
    
    for src, dst in replacements.items():
        text = text.replace(src, dst)
        
    # 3. Remove Punctuation and Special Characters
    # Keep alphanumeric and spaces only
    text = re.sub(r'[^\w\s]', '', text)
    
    # 4. Collapse Whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def calculate_fuzzy_score(query: str, target: str) -> int:
    """
    Calculate fuzzy matching score between query and target (0-100).
    Uses RapidFuzz for performance.
    
    Args:
        query (str): The search term (already normalized recommended)
        target (str): The text to search in (already normalized recommended)
        
    Returns:
        int: Score from 0 to 100
    """
    try:
        from rapidfuzz import fuzz
        # partial_ratio allows "yanilsamlar" to match "metafizik yanilsamalar" strongly
        return fuzz.partial_ratio(query, target)
    except ImportError:
        # Fallback if rapidfuzz not present (though it should be)
        return 0

# --- Phase 1: New NLP Functions ---
import unidecode
try:
    import zeyrek
    _analyzer = zeyrek.MorphAnalyzer()
except ImportError:
    _analyzer = None
    print("[WARNING] Zeyrek not found. Lemmatization will be disabled.")

def normalize_canonical(text: str) -> str:
    """
    Turkish-aware normalization aiming to preserve characters (NFC) 
    but standardized (lowercase, no weird punctuation).
    Used for Lemmatization inputs.
    """
    if not text: return ""
    text = unicodedata.normalize('NFC', text)
    # Turkish lowercase
    text = text.replace('İ', 'i').replace('I', 'ı')
    text = text.lower()
    # Remove punctuation but KEEP Turkish chars
    text = re.sub(r'[^\w\s]', '', text) 
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def deaccent_text(text: str) -> str:
    """
    Aggressive de-accenting using existing normalize_text (which does transliteration).
    """
    return normalize_text(text)

def get_lemmas(text: str) -> list[str]:
    """
    Extracts unique lemmas (roots) from text using Zeyrek.
    Input must contain original Turkish characters for best results.
    """
    if not text or not _analyzer:
        return []
    
    lemmas = set()
    try:
        # Use Canonical (Accents preserved) for Zeyrek
        canonical = normalize_canonical(text)
        
        results = _analyzer.analyze(canonical)
        for word_analysis in results:
            for parse in word_analysis:
                if parse.lemma and parse.lemma.lower() not in ['unk', 'unknown']:
                     lemmas.add(parse.lemma.lower())
                     
    except Exception as e:
        pass
        
    return list(lemmas)


def get_lemma_frequencies(text: str) -> dict[str, int]:
    """
    Extracts lemma frequencies from text using Zeyrek.
    Returns a dict of lemma -> count.
    """
    if not text or not _analyzer:
        return {}

    freqs: dict[str, int] = {}
    try:
        canonical = normalize_canonical(text)
        results = _analyzer.analyze(canonical)
        for word_analysis in results:
            if not word_analysis:
                continue
            # Use the first parse for determinism
            parse = word_analysis[0]
            lemma = parse.lemma.lower() if parse.lemma else None
            if not lemma or lemma in ['unk', 'unknown']:
                continue
            freqs[lemma] = freqs.get(lemma, 0) + 1
    except Exception:
        return {}

    return freqs
