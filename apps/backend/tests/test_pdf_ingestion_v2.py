from types import SimpleNamespace

from services.canonical_document_service import CanonicalBlock, CanonicalDocument, CanonicalPage, merge_documents
from services.chunk_render_service import render_document_chunks, summarize_chunk_metrics
from services.ingestion_status_service import is_active_parse_status
from services.paragraph_reconstruction_service import reconstruct_document
from services.pdf_classifier_service import classify_pdf, decide_route
from services.pdf_async_ingestion_service import _resolve_processing_route
from services.pdf_parser_adapters import LlamaParseAdapter, _canonicalize_ocr_payload, _parse_language_values


def _document(blocks):
    return CanonicalDocument(
        document_id="doc-1",
        route="TEXT_NATIVE",
        parser_engine="PYMUPDF",
        parser_version="v1",
        pages=[
            CanonicalPage(
                page_number=1,
                has_text_layer=True,
                char_count=200,
                word_count=40,
                ocr_applied=False,
                image_heavy_suspected=False,
                garbled_ratio=0.01,
            ),
            CanonicalPage(
                page_number=2,
                has_text_layer=True,
                char_count=220,
                word_count=42,
                ocr_applied=False,
                image_heavy_suspected=False,
                garbled_ratio=0.01,
            ),
        ],
        blocks=blocks,
        classifier_metrics={},
        quality_metrics={},
        routing_metrics={},
    )


def test_decide_route_prefers_text_native_when_preflight_is_clean():
    route = decide_route(
        {
            "page_count": 120,
            "pages_with_text_ratio": 0.94,
            "avg_chars_per_page": 880,
            "blank_page_ratio": 0.01,
            "garbled_ratio": 0.02,
            "image_heavy_ratio": 0.10,
        }
    )
    assert route == "TEXT_NATIVE"


def test_resolve_processing_route_uses_classifier_result():
    classifier_result = SimpleNamespace(route="TEXT_NATIVE")
    assert _resolve_processing_route(classifier_result) == "TEXT_NATIVE"


def test_reconstruct_document_merges_page_boundary_continuation():
    doc = _document(
        [
            CanonicalBlock(
                block_id="b1",
                page_number=1,
                block_type="body",
                text="Bu paragraf sonraki sayfada devam eden",
                reading_order=0,
                heading_path=["Bolum 1"],
                source_engine="PYMUPDF",
            ),
            CanonicalBlock(
                block_id="b2",
                page_number=2,
                block_type="body",
                text="ve yine ayni cumleye baglanan kisimdir.",
                reading_order=1,
                heading_path=["Bolum 1"],
                source_engine="PYMUPDF",
            ),
        ]
    )
    reconstructed = reconstruct_document(doc)
    body_blocks = [block for block in reconstructed.blocks if block.block_type == "body"]
    assert len(body_blocks) == 1
    assert "baglanan kisimdir" in body_blocks[0].text
    assert reconstructed.quality_metrics["page_boundary_merge_total"] == 1


def test_reconstruct_document_strips_repeated_margin_blocks(monkeypatch):
    monkeypatch.setattr("services.paragraph_reconstruction_service.settings.PDF_HEADER_FOOTER_SAMPLE_DEPTH", 2)
    monkeypatch.setattr("services.paragraph_reconstruction_service.settings.PDF_HEADER_FOOTER_MIN_OCCURRENCES", 3)
    monkeypatch.setattr("services.paragraph_reconstruction_service.settings.PDF_HEADER_FOOTER_REPEAT_RATIO_MIN", 0.2)

    doc = CanonicalDocument(
        document_id="doc-margin",
        route="IMAGE_SCAN",
        parser_engine="LLAMAPARSE",
        parser_version="v1",
        pages=[
            CanonicalPage(1, False, 0, 0, True, True, 0.0),
            CanonicalPage(2, False, 0, 0, True, True, 0.0),
            CanonicalPage(3, False, 0, 0, True, True, 0.0),
        ],
        blocks=[
            CanonicalBlock("p1h", 1, "heading", "Chapter 1", reading_order=0, source_engine="LLAMAPARSE"),
            CanonicalBlock("p1b", 1, "body", "Bu sayfadaki asil govde metni yeterince uzundur ve korunmalidir.", reading_order=1, source_engine="LLAMAPARSE"),
            CanonicalBlock("p1f", 1, "body", "Page 1", reading_order=2, source_engine="LLAMAPARSE"),
            CanonicalBlock("p2h", 2, "heading", "Chapter 1", reading_order=3, source_engine="LLAMAPARSE"),
            CanonicalBlock("p2b", 2, "body", "Ikinci sayfadaki govde metni de semantic olarak tutulmalidir.", reading_order=4, source_engine="LLAMAPARSE"),
            CanonicalBlock("p2f", 2, "body", "Page 2", reading_order=5, source_engine="LLAMAPARSE"),
            CanonicalBlock("p3h", 3, "heading", "Chapter 1", reading_order=6, source_engine="LLAMAPARSE"),
            CanonicalBlock("p3b", 3, "body", "Ucuncu sayfadaki govde metni de header footer disinda kalir.", reading_order=7, source_engine="LLAMAPARSE"),
            CanonicalBlock("p3f", 3, "body", "Page 3", reading_order=8, source_engine="LLAMAPARSE"),
        ],
        classifier_metrics={},
        quality_metrics={},
        routing_metrics={},
    )

    reconstructed = reconstruct_document(doc)
    texts = [block.text for block in reconstructed.blocks]

    assert all(text != "Chapter 1" for text in texts)
    assert all(not text.startswith("Page ") for text in texts)
    assert reconstructed.quality_metrics["header_footer_removed_total"] == 6
    assert any("asil govde metni" in text for text in texts)


def test_render_document_chunks_keeps_context_prefix():
    doc = _document(
        [
            CanonicalBlock(
                block_id="h1",
                page_number=1,
                block_type="heading",
                text="Bolum 1",
                reading_order=0,
                heading_path=["Bolum 1"],
                source_engine="PYMUPDF",
            ),
            CanonicalBlock(
                block_id="b1",
                page_number=1,
                block_type="body",
                text="Bu birinci paragraftir ve yeterince uzundur ki chunk icine girsin.",
                reading_order=1,
                heading_path=["Bolum 1"],
                context_prefix="Bolum 1",
                source_engine="PYMUPDF",
            ),
            CanonicalBlock(
                block_id="b2",
                page_number=1,
                block_type="body",
                text="Bu da ikinci paragraftir ve ayni baslik altinda ilerler.",
                reading_order=2,
                heading_path=["Bolum 1"],
                context_prefix="Bolum 1",
                source_engine="PYMUPDF",
            ),
        ]
    )
    chunks = render_document_chunks(doc)
    metrics = summarize_chunk_metrics(chunks)
    assert chunks
    assert chunks[0]["context_prefix"] == "Bolum 1"
    assert chunks[0]["rendered_context_prefix"].startswith("## Bolum 1")
    assert metrics["chunk_count"] >= 1


def test_render_document_chunks_prefers_sentence_boundaries(monkeypatch):
    monkeypatch.setattr("services.chunk_render_service.settings.PDF_SENTENCE_CHUNKING_ENABLED", True)
    monkeypatch.setattr("services.chunk_render_service.settings.PDF_CHUNK_OVERLAP_TOKENS", 0)
    monkeypatch.setattr("services.chunk_render_service.settings.PDF_CHUNK_SOFT_TOKEN_TARGET", 12)
    monkeypatch.setattr("services.chunk_render_service.settings.PDF_CHUNK_HARD_TOKEN_CAP", 18)

    doc = _document(
        [
            CanonicalBlock(
                block_id="b1",
                page_number=1,
                block_type="body",
                text=(
                    "Birinci cumle burada biter. "
                    "Ikinci cumle de burada tamamlanir. "
                    "Ucuncu cumle ayrica yeterince uzundur. "
                    "Dorduncu cumle son olarak eklenir."
                ),
                reading_order=0,
                heading_path=["Bolum 1"],
                context_prefix="Bolum 1",
                source_engine="PYMUPDF",
            ),
        ]
    )

    chunks = render_document_chunks(doc)

    assert len(chunks) >= 2
    assert all(chunk["text"].strip() for chunk in chunks)
    assert all(chunk["text"].strip()[-1] in ".!?" for chunk in chunks[:-1])
    assert chunks[1]["text"].startswith(("Ikinci", "Ucuncu", "Dorduncu"))


def test_render_document_chunks_splits_large_table_with_header_prefix():
    table_text = "\n".join(
        [
            "Tablo 1: Baslik",
            "Kolon A | Kolon B",
            *[f"Satir {idx} | Deger {idx}" for idx in range(1, 140)],
        ]
    )
    doc = CanonicalDocument(
        document_id="doc-table",
        route="IMAGE_SCAN",
        parser_engine="LLAMAPARSE",
        parser_version="v1",
        pages=[
            CanonicalPage(
                page_number=1,
                has_text_layer=False,
                char_count=0,
                word_count=0,
                ocr_applied=True,
                image_heavy_suspected=True,
                garbled_ratio=0.0,
            )
        ],
        blocks=[
            CanonicalBlock(
                block_id="t1",
                page_number=1,
                block_type="table",
                text=table_text,
                reading_order=0,
                heading_path=["Ekler"],
                source_engine="LLAMAPARSE",
            )
        ],
        classifier_metrics={},
        quality_metrics={},
        routing_metrics={},
    )

    chunks = render_document_chunks(doc)

    assert len(chunks) > 1
    assert all(chunk["text"].startswith("Tablo 1: Baslik\nKolon A | Kolon B") for chunk in chunks)


def test_parse_language_values_splits_csv():
    assert _parse_language_values("tr,en") == ["tr", "en"]
    assert _parse_language_values("tr") == ["tr"]
    assert _parse_language_values("") == ["tr"]


def test_llamaparse_adapter_sends_languages_as_repeated_form_fields(monkeypatch, tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

    captured = {}

    class FakeParseResult:
        def model_dump(self, mode="json"):
            return {
                "items": {
                    "pages": [
                        {
                            "page_number": 1,
                            "success": True,
                            "items": [
                                {
                                    "type": "text",
                                    "value": "Merhaba dunya",
                                    "bbox": [{"x": 1, "y": 2, "w": 30, "h": 10}],
                                }
                            ],
                        }
                    ]
                }
            }

    class FakeFiles:
        def create(self, *, file, purpose):
            captured["file"] = file
            captured["purpose"] = purpose
            return SimpleNamespace(id="file-123")

    class FakeParsing:
        def parse(self, **kwargs):
            captured["parse_kwargs"] = kwargs
            return FakeParseResult()

    class FakeLlamaCloud:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.files = FakeFiles()
            self.parsing = FakeParsing()

    monkeypatch.setattr("services.pdf_parser_adapters.LlamaCloud", FakeLlamaCloud, raising=False)
    monkeypatch.setattr("services.pdf_parser_adapters.settings.LLAMA_CLOUD_API_KEY", "test-key")
    monkeypatch.setattr("services.pdf_parser_adapters.settings.PDF_OCR_LANGUAGES", "tr,en")
    monkeypatch.setattr("services.pdf_parser_adapters.settings.LLAMA_PARSE_TIMEOUT_SEC", 1)
    monkeypatch.setattr("services.pdf_parser_adapters.settings.LLAMA_PARSE_POLL_INTERVAL_SEC", 1)
    monkeypatch.setattr("services.pdf_parser_adapters.settings.LLAMA_PARSE_TIER", "agentic")
    monkeypatch.setattr("services.pdf_parser_adapters.settings.LLAMA_PARSE_VERSION", "latest")

    document = LlamaParseAdapter().parse(
        pdf_path=str(pdf_path),
        document_id="doc-1",
        route="IMAGE_SCAN",
        classifier_result=SimpleNamespace(
            classifier_metrics={"page_count": 1},
            pages=[
                SimpleNamespace(
                    page_number=1,
                    has_text_layer=False,
                    char_count=0,
                    word_count=0,
                    image_heavy_suspected=True,
                    garbled_ratio=0.0,
                )
            ],
        ),
    )

    assert document.parser_engine == "LLAMAPARSE"
    assert captured["api_key"] == "test-key"
    assert captured["purpose"] == "parse"
    assert captured["parse_kwargs"]["processing_options"]["ocr_parameters"]["languages"] == ["tr", "en"]
    assert captured["parse_kwargs"]["output_options"]["spatial_text"]["preserve_layout_alignment_across_pages"] is True


def test_canonicalize_ocr_payload_flattens_items_pages_shape():
    document = _canonicalize_ocr_payload(
        document_id="doc-1",
        route="IMAGE_SCAN",
        parser_engine="LLAMAPARSE",
        parser_version="v1",
        payload={
            "items": {
                "pages": [
                    {
                        "page_number": 3,
                        "success": True,
                        "items": [
                            {
                                "type": "heading",
                                "value": "Bolum 3",
                                "bbox": [{"x": 10, "y": 20, "w": 30, "h": 5}],
                            },
                            {
                                "type": "text",
                                "value": "Metin govdesi",
                                "bbox": [{"x": 15, "y": 30, "w": 50, "h": 10}],
                            },
                        ],
                    }
                ]
            }
        },
        classifier_result=SimpleNamespace(
            classifier_metrics={"page_count": 1},
            pages=[
                SimpleNamespace(
                    page_number=3,
                    has_text_layer=False,
                    char_count=0,
                    word_count=0,
                    image_heavy_suspected=True,
                    garbled_ratio=0.0,
                )
            ],
        ),
        ocr_applied=True,
    )

    assert len(document.blocks) == 2
    assert document.blocks[0].page_number == 3
    assert document.blocks[0].block_type == "heading"
    assert document.blocks[0].bbox == {"x0": 10.0, "y0": 20.0, "x1": 40.0, "y1": 25.0}


def test_merge_documents_dedupes_pages_after_shard_offset():
    left = CanonicalDocument(
        document_id="doc-1",
        route="IMAGE_SCAN",
        parser_engine="LLAMAPARSE",
        parser_version="v1",
        pages=[
            CanonicalPage(1, False, 0, 0, True, True, 0.0),
            CanonicalPage(2, False, 0, 0, True, True, 0.0),
        ],
        blocks=[
            CanonicalBlock("b1", 1, "text", "sol", reading_order=0, source_engine="LLAMAPARSE"),
            CanonicalBlock("b2", 2, "text", "orta", reading_order=1, source_engine="LLAMAPARSE"),
        ],
    )
    right = CanonicalDocument(
        document_id="doc-1",
        route="IMAGE_SCAN",
        parser_engine="LLAMAPARSE",
        parser_version="v1",
        pages=[
            CanonicalPage(2, False, 10, 2, True, True, 0.0),
            CanonicalPage(3, False, 0, 0, True, True, 0.0),
        ],
        blocks=[
            CanonicalBlock("b3", 2, "text", "iki", reading_order=0, source_engine="LLAMAPARSE"),
            CanonicalBlock("b4", 3, "text", "uc", reading_order=1, source_engine="LLAMAPARSE"),
        ],
    )

    merged = merge_documents(
        document_id="doc-1",
        route="IMAGE_SCAN",
        parser_engine="LLAMAPARSE",
        parser_version="v1",
        documents=[left, right],
    )

    assert [page.page_number for page in merged.pages] == [1, 2, 3]
    assert len(merged.blocks) == 4


def test_is_active_parse_status_only_for_live_processing_rows():
    assert is_active_parse_status("PROCESSING", "QUEUED") is True
    assert is_active_parse_status("PROCESSING", "PARSING") is True
    assert is_active_parse_status("PROCESSING", "COMPLETED") is False
    assert is_active_parse_status("FAILED", "FAILED") is False


class _FakeClassifierPage:
    def __init__(self, text: str, image_count: int = 1):
        self._text = text
        self._image_count = image_count

    def get_text(self, _mode: str, sort: bool = True):
        return self._text

    def get_images(self, full: bool = True):
        return [object()] * self._image_count


class _FakeClassifierDocument:
    def __init__(self, pages):
        self._pages = pages

    def __len__(self):
        return len(self._pages)

    def load_page(self, idx: int):
        return self._pages[idx]


def test_classify_pdf_uses_progressive_early_exit_for_clear_ocr_cases(monkeypatch, tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")

    fake_document = _FakeClassifierDocument(
        [_FakeClassifierPage("", image_count=2) for _ in range(80)]
    )

    monkeypatch.setattr("services.pdf_classifier_service._require_pymupdf", lambda: SimpleNamespace(open=lambda _: fake_document))
    monkeypatch.setattr("services.pdf_classifier_service.settings.PDF_CLASSIFIER_EARLY_OCR_ENABLED", True)
    monkeypatch.setattr("services.pdf_classifier_service.settings.PDF_CLASSIFIER_SAMPLE_PAGES", 5)
    monkeypatch.setattr("services.pdf_classifier_service.settings.PDF_TEXT_NATIVE_MIN_CHARS_PER_PAGE", 120)
    monkeypatch.setattr("services.pdf_classifier_service.settings.PDF_TEXT_NATIVE_TEXT_PAGE_RATIO_MIN", 0.7)
    monkeypatch.setattr("services.pdf_classifier_service.settings.PDF_TEXT_NATIVE_IMAGE_HEAVY_RATIO_MAX", 0.4)

    result = classify_pdf(str(pdf_path))

    assert result.route == "IMAGE_SCAN"
    assert result.classifier_metrics["early_exit_ocr"] is True
    assert result.classifier_metrics["route_reason"] == "sample_no_text"
    assert result.classifier_metrics["sampled_page_count"] >= 3
    assert len(result.pages) == 80
