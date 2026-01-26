
import os
from rapidfuzz import process, fuzz

class SpellChecker:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SpellChecker, cls).__new__(cls)
            cls._instance.vocab = []
            cls._instance.loaded = False
        return cls._instance

    def load_dictionary(self):
        if self.loaded:
            return

        current_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(current_dir)
        dict_path = os.path.join(backend_dir, 'data', 'dictionary.txt')
        
        if os.path.exists(dict_path):
            print(f"[INFO] Loading Spell Dictionary from {dict_path}")
            try:
                vocab = []
                with open(dict_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        parts = line.split()
                        if parts:
                            vocab.append(parts[0])
                self.vocab = vocab
                self.loaded = True
                print(f"[INFO] Loaded {len(vocab)} words into Spell Checker.")
            except Exception as e:
                print(f"[ERROR] Failed to load dictionary: {e}")
        else:
            print("[WARNING] dictionary.txt not found. Spell checking disabled.")

    def correct(self, text: str) -> str:
        if not self.loaded or not text or len(text) < 3:
            return text
            
        # Check if word exists in vocab (Exact match)
        # Note: rapidfuzz process.extractOne is slower if we have huge vocab, but for <2000 words it's instant.
        # Ideally we use a set for exact check.
        
        # Simple Logic: If text is in vocab, return it.
        # If not, find closest.
        
        # For multi-word queries, this simple looping correction is naive but okay for Phase 2.
        words = text.split()
        corrected_words = []
        for word in words:
            # Skip short words
            if len(word) < 3:
                corrected_words.append(word)
                continue
                
            # Exact check (case insensitive)
            # Optimization: could make self.vocab a set for O(1) check
            
            match = process.extractOne(word, self.vocab, scorer=fuzz.ratio)
            # match is (string, score, index)
            if match:
                candidate, score, _ = match
                if score >= 90: # Exact or super close
                     corrected_words.append(candidate)
                elif score > 80: # Typo correction threshold
                     corrected_words.append(candidate)
                else:
                     corrected_words.append(word)
            else:
                 corrected_words.append(word)
                 
        return " ".join(corrected_words)

# Singleton Accessor
_checker = SpellChecker()

def get_spell_checker():
    _checker.load_dictionary()
    return _checker
