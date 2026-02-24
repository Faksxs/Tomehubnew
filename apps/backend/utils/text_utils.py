import re
import unicodedata


_MOJIBAKE_MARKERS = ("Ã", "Ä", "Å", "Â", "â", "�")


def repair_common_mojibake(text: str) -> str:
    """
    Best-effort repair for UTF-8 text that was decoded with latin-1/cp1252.
    Leaves the input unchanged when no clear mojibake markers are present.
    """
    if not text:
        return ""
    if not any(marker in text for marker in _MOJIBAKE_MARKERS):
        return text

    candidates = [text]
    for enc in ("latin-1", "cp1252"):
        try:
            candidates.append(text.encode(enc).decode("utf-8"))
        except Exception:
            continue

    def _score(value: str) -> tuple[int, int]:
        marker_penalty = sum(value.count(m) for m in _MOJIBAKE_MARKERS)
        turkish_bonus = sum(value.count(ch) for ch in "çğıöşüÇĞİÖŞÜ")
        return (-marker_penalty, turkish_bonus)

    return max(candidates, key=_score)


def normalize_text(text: str) -> str:
    """
    Turkish-aware normalization for search.

    1. Repair common mojibake (best effort)
    2. Lowercase with Turkish awareness (I -> ı, İ -> i)
    3. ASCII transliteration (ş -> s, ç -> c, ğ -> g, etc.)
    4. Punctuation removal
    5. Collapse whitespace
    """
    if not text:
        return ""

    text = repair_common_mojibake(text)
    text = unicodedata.normalize("NFC", text)

    # Turkish lowercase mapping before .lower()
    text = text.replace("İ", "i").replace("I", "ı")
    text = text.lower()

    replacements = {
        "ı": "i",
        "ş": "s",
        "ç": "c",
        "ğ": "g",
        "ü": "u",
        "ö": "o",
        "â": "a",
        "î": "i",
        "û": "u",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def calculate_fuzzy_score(query: str, target: str) -> int:
    """
    Calculate fuzzy matching score between query and target (0-100).
    Uses RapidFuzz for performance.
    """
    try:
        from rapidfuzz import fuzz

        return fuzz.partial_ratio(query, target)
    except ImportError:
        return 0


# --- Phase 1: New NLP Functions ---
import unidecode  # noqa: F401  # Kept for compatibility/import side effects in older callers

try:
    import zeyrek

    _analyzer = zeyrek.MorphAnalyzer()
except ImportError:
    _analyzer = None
    print("[WARNING] Zeyrek not found. Lemmatization will be disabled.")


def normalize_canonical(text: str) -> str:
    """
    Turkish-aware normalization preserving Turkish chars for lemmatization.
    """
    if not text:
        return ""
    text = repair_common_mojibake(text)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("İ", "i").replace("I", "ı")
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def deaccent_text(text: str) -> str:
    """
    Aggressive de-accenting using normalize_text transliteration.
    """
    return normalize_text(text)


def get_lemmas(text: str) -> list[str]:
    """
    Extract unique lemmas (roots) from text using Zeyrek.
    """
    if not text or not _analyzer:
        return []

    lemmas: set[str] = set()
    try:
        canonical = normalize_canonical(text)
        results = _analyzer.analyze(canonical)
        for word_analysis in results:
            for parse in word_analysis:
                if parse.lemma and parse.lemma.lower() not in ["unk", "unknown"]:
                    lemmas.add(parse.lemma.lower())
    except Exception:
        pass

    return list(lemmas)


def get_lemma_frequencies(text: str) -> dict[str, int]:
    """
    Extract lemma frequencies from text using Zeyrek.
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
            parse = word_analysis[0]
            lemma = parse.lemma.lower() if parse.lemma else None
            if not lemma or lemma in ["unk", "unknown"]:
                continue
            freqs[lemma] = freqs.get(lemma, 0) + 1
    except Exception:
        return {}

    return freqs
