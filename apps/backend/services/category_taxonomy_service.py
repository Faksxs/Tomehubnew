from __future__ import annotations

import unicodedata
from typing import Iterable, List, Optional


# Canonical UI/BOOK taxonomy (12 fixed categories).
BOOK_CATEGORIES: List[str] = [
    'Felsefe',
    'Sosyoloji',
    'Psikoloji',
    'Siyaset ve Politika',
    'Din ve İnanç',
    'Tarih ve Medeniyet',
    'Ekonomi ve Hukuk',
    'Türk Edebiyatı',
    'Dünya Edebiyatı',
    'Kültür ve Sanat',
    'Diğer',
]


def _norm(value: str) -> str:
    text = str(value or '').strip().lower()
    if not text:
        return ''
    text = (
        text.replace('ı', 'i')
        .replace('İ', 'i')
        .replace('â', 'a')
        .replace('î', 'i')
        .replace('û', 'u')
    )
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    cleaned = []
    for ch in text:
        cleaned.append(ch if (ch.isalnum() or ch.isspace()) else ' ')
    return ' '.join(''.join(cleaned).split())


_CANONICAL_BY_NORM = {_norm(x): x for x in BOOK_CATEGORIES}

# Backward-compat aliases / historic labels.
_ALIASES = {
    _norm('Siyaset Bilimi'): 'Siyaset ve Politika',
    _norm('Politika'): 'Siyaset ve Politika',
    _norm('Siyaset'): 'Siyaset ve Politika',
    _norm('Bilim ve Teknoloji'): 'Diğer',
    _norm('İnceleme ve Araştırma'): 'Diğer',
    _norm('Tarih'): 'Tarih ve Medeniyet',
    _norm('Sanat ve Kültür'): 'Kültür ve Sanat',
    _norm('Kultur ve Sanat'): 'Kültür ve Sanat',
    _norm('Din ve Inanc'): 'Din ve İnanç',
    _norm('Turk Edebiyati'): 'Türk Edebiyatı',
    _norm('Dunya Edebiyati'): 'Dünya Edebiyatı',
    _norm('Diger'): 'Diğer',
    # Mojibake variants observed in legacy UI/category tags
    _norm('Din ve Ä°nanÃ§'): 'Din ve İnanç',
    _norm('TÃ¼rk EdebiyatÄ±'): 'Türk Edebiyatı',
    _norm('DÃ¼nya EdebiyatÄ±'): 'Dünya Edebiyatı',
    _norm('Sanat ve KÃ¼ltÃ¼r'): 'Sanat ve Kültür',
    _norm('DiÄŸer'): 'Diğer',
    _norm('Ä°nceleme ve AraÅŸtÄ±rma'): 'Diğer',
}


def normalize_book_category_label(value: str) -> Optional[str]:
    key = _norm(value)
    if not key:
        return None
    if key in _CANONICAL_BY_NORM:
        return _CANONICAL_BY_NORM[key]
    return _ALIASES.get(key)


def extract_book_categories_from_tags(tags: Iterable[str] | None) -> List[str]:
    out: List[str] = []
    seen = set()
    if not tags:
        return out
    for tag in tags:
        canonical = normalize_book_category_label(str(tag or ''))
        if not canonical:
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        out.append(canonical)
    return out


def replace_legacy_category_tag(value: str) -> str:
    canonical = normalize_book_category_label(value)
    if canonical:
        return canonical
    return str(value or '')
