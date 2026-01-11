
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
