import unittest

from infrastructure.db_manager import safe_read_clob


class _ChunkReadable:
    def __init__(self, text: str):
        self._text = text
        self._idx = 0

    def read(self, size: int):
        if self._idx >= len(self._text):
            return ""
        out = self._text[self._idx : self._idx + size]
        self._idx += size
        return out


class _NoSizeReadable:
    def __init__(self, text: str):
        self._text = text

    def read(self):
        return self._text


class _OracleLikeReadable:
    """Simulates Oracle LOB.read(offset, amount) semantics."""
    def __init__(self, text: str):
        self._text = text

    def read(self, offset: int = 1, amount: int | None = None):
        start = max(0, int(offset) - 1)
        if start >= len(self._text):
            return ""
        if amount is None:
            return self._text[start:]
        end = start + int(amount)
        return self._text[start:end]


class SafeReadClobTests(unittest.TestCase):
    def test_none_returns_empty_string(self):
        out = safe_read_clob(None)
        self.assertEqual(out, "")

    def test_respects_max_chars_with_chunked_reader(self):
        src = _ChunkReadable("x" * 200)
        out = safe_read_clob(src, max_chars=50, chunk_size=10)
        self.assertEqual(len(out), 50)

    def test_respects_max_chars_with_no_size_reader(self):
        src = _NoSizeReadable("y" * 200)
        out = safe_read_clob(src, max_chars=40)
        self.assertEqual(len(out), 40)

    def test_handles_plain_string(self):
        out = safe_read_clob("abc" * 100, max_chars=10)
        self.assertEqual(len(out), 10)

    def test_oracle_like_reader_uses_offset_amount_correctly(self):
        src = _OracleLikeReadable("z" * 180)
        out = safe_read_clob(src, max_chars=90, chunk_size=25)
        self.assertEqual(len(out), 90)
        self.assertEqual(out, "z" * 90)


if __name__ == "__main__":
    unittest.main()
