import re
import os
import ftfy
# Replaced SymSpell with RapidFuzz due to build issues on Windows without C++ tools
from rapidfuzz import process, fuzz
import logging

logger = logging.getLogger(__name__)

class LinguisticCorrectionService:
    RULE_VERSION = "tr_ocr_v1"
    
    # Common OCR artifact replacements (high precision)
    REGEX_RULES = [
        # 1. Tilde repairs (Aggressive)
        (r'~alisma', 'çalışma'),
        (r'~', 'ş'), # Fallback
        
        # 2. Known "Hayat" book specific errors
        (r'\bgPnOmuz\b', 'günümüz'),
        (r'\bgOnOmuz\b', 'günümüz'),
        (r'\bgonomuz\b', 'günümüz'),
        
        # 3. General "O" / "0" -> "ü" / "ö" fixer (Heuristic)
        (r'\bg[O0]n\b', 'gün'),
        (r'\bb[O0]t[O0]n\b', 'bütün'),
        (r'\bg[O0]z\b', 'göz'),
        (r'\bk[O0]lt[O0]r\b', 'kültür'),
        
        # 4. "1" -> "ı" fixer
        (r'([a-z])1\b', r'\1ı'),
    ]

    def __init__(self):
        self.valid_words = set()
        self._load_bootstrap_dictionary()

    def _load_bootstrap_dictionary(self):
        """
        Loads a small bootstrap dictionary.
        """
        # Dictionary of valid words
        bootstrap_words = """
        günümüz
        kültür
        bütün
        göz
        hayat
        anlam
        insan
        felsefe
        toplum
        çalışma
        bağlı
        olarak
        bir
        bu
        var
        yok
        için
        """
        self.valid_words = {w.strip() for w in bootstrap_words.strip().split() if w.strip()}

    def fix_text(self, text: str) -> str:
        if not text:
            return ""

        # Step 0: FTFY
        text = ftfy.fix_text(text)

        # Step 1: Line Gluestick
        text = re.sub(r'(\w+)-\s*\n\s*([a-zğüşiöç]+)', r'\1\2\n', text)
        
        # Step 3: Regex "Sledgehammer"
        for pattern, replacement in self.REGEX_RULES:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        # Step 4: Dictionary checks (Optional for now/future expansion)
        # Using RapidFuzz here might be slow for entire texts, so we skip it 
        # for this MVP pass unless specific problematic words are identified.
        # The Regex rules above handle the specific 'Hayat' errors (gOnOmuz -> günümüz).

        return text

    def verify_word(self, word: str):
        """Debug helper to test fuzzy match"""
        match = process.extractOne(word, self.valid_words, scorer=fuzz.ratio)
        return match
