from utils.isbn_utils import (
    compact_isbn,
    equivalent_isbn_set,
    is_valid_isbn10,
    is_valid_isbn13,
    normalize_valid_isbn,
)


def test_compact_isbn_strips_noise():
    assert compact_isbn("ISBN 978-975-07-2131-1") == "9789750721311"


def test_isbn_validation():
    assert is_valid_isbn13("9789750721311")
    assert not is_valid_isbn13("9789750721312")
    assert is_valid_isbn10("9750721314")
    assert not is_valid_isbn10("9750721318")


def test_normalize_valid_isbn_and_equivalents():
    assert normalize_valid_isbn("978-975-07-2131-1") == "9789750721311"
    eq = equivalent_isbn_set("9789750721311")
    assert "9789750721311" in eq
    assert "9750721314" in eq
