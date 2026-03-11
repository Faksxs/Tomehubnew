import unittest
from unittest.mock import AsyncMock, patch

from services import pdf_metadata_service


class _FakePage:
    def __init__(self, text: str):
        self._text = text

    def get_text(self, _mode: str, sort: bool = True):
        return self._text


class _FakeDocument:
    def __init__(self, page_text: str, *, title: str | None = None, author: str | None = None, page_count: int = 1):
        self.metadata = {"title": title, "author": author}
        self._page = _FakePage(page_text)
        self._page_count = page_count
        self.closed = False

    def __len__(self):
        return self._page_count

    def load_page(self, _idx: int):
        return self._page

    def close(self):
        self.closed = True


class PdfMetadataServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_ai_metadata_overrides_embedded_fields(self):
        fake_doc = _FakeDocument(
            "Belge basligi burada yaziyor. Yazari da burada geciyor.",
            title="Embedded Title",
            author="Embedded Author",
            page_count=12,
        )

        with patch.object(pdf_metadata_service, "_open_pymupdf_document", return_value=fake_doc):
            with patch.object(
                pdf_metadata_service,
                "extract_metadata_from_text_async",
                AsyncMock(return_value={"title": "AI Title", "author": "AI Author"}),
            ):
                result = await pdf_metadata_service.get_pdf_metadata("dummy.pdf")

        self.assertEqual(result["page_count"], 12)
        self.assertEqual(result["title"], "AI Title")
        self.assertEqual(result["author"], "AI Author")
        self.assertTrue(fake_doc.closed)

    async def test_embedded_metadata_is_used_when_ai_returns_empty(self):
        fake_doc = _FakeDocument(
            "Kisa metin",
            title="Embedded Title",
            author="Embedded Author",
            page_count=3,
        )

        with patch.object(pdf_metadata_service, "_open_pymupdf_document", return_value=fake_doc):
            with patch.object(
                pdf_metadata_service,
                "extract_metadata_from_text_async",
                AsyncMock(return_value={"title": None, "author": None}),
            ):
                result = await pdf_metadata_service.get_pdf_metadata("dummy.pdf")

        self.assertEqual(result["page_count"], 3)
        self.assertEqual(result["title"], "Embedded Title")
        self.assertEqual(result["author"], "Embedded Author")
        self.assertTrue(fake_doc.closed)


if __name__ == "__main__":
    unittest.main()
