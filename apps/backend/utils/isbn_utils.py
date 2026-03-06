from __future__ import annotations

from typing import Any, Optional, Set


def compact_isbn(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit() or ch.upper() == "X").upper()


def is_valid_isbn10(isbn: str) -> bool:
    if len(isbn) != 10:
        return False
    if not isbn[:9].isdigit():
        return False
    if not (isbn[9].isdigit() or isbn[9] == "X"):
        return False
    total = 0
    for idx, ch in enumerate(isbn):
        digit = 10 if ch == "X" else int(ch)
        total += digit * (10 - idx)
    return total % 11 == 0


def is_valid_isbn13(isbn: str) -> bool:
    if len(isbn) != 13 or not isbn.isdigit():
        return False
    total = 0
    for idx in range(12):
        total += int(isbn[idx]) * (1 if idx % 2 == 0 else 3)
    check = (10 - (total % 10)) % 10
    return check == int(isbn[12])


def isbn10_to13(isbn10: str) -> Optional[str]:
    if not is_valid_isbn10(isbn10):
        return None
    core = f"978{isbn10[:9]}"
    total = 0
    for idx in range(12):
        total += int(core[idx]) * (1 if idx % 2 == 0 else 3)
    check = (10 - (total % 10)) % 10
    return f"{core}{check}"


def isbn13_to10(isbn13: str) -> Optional[str]:
    if not (is_valid_isbn13(isbn13) and isbn13.startswith("978")):
        return None
    core = isbn13[3:12]
    total = 0
    for idx in range(9):
        total += int(core[idx]) * (10 - idx)
    rem = 11 - (total % 11)
    check = "X" if rem == 10 else ("0" if rem == 11 else str(rem))
    return f"{core}{check}"


def normalize_valid_isbn(value: Any) -> Optional[str]:
    raw = compact_isbn(value)
    if len(raw) == 13 and is_valid_isbn13(raw):
        return raw
    if len(raw) == 10 and is_valid_isbn10(raw):
        return raw
    return None


def equivalent_isbn_set(value: Any) -> Set[str]:
    normalized = normalize_valid_isbn(value)
    if not normalized:
        return set()
    out: Set[str] = {normalized}
    if len(normalized) == 10:
        alt = isbn10_to13(normalized)
        if alt:
            out.add(alt)
    elif len(normalized) == 13:
        alt = isbn13_to10(normalized)
        if alt:
            out.add(alt)
    return out


def safe_isbn_from_input(value: Any) -> Optional[str]:
    # Intentionally permissive: used for preserving user-provided ISBN
    # without trusting LLM-generated values.
    raw = compact_isbn(value)
    if len(raw) in (10, 13):
        return raw
    return None

