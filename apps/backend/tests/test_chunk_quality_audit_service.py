from services.chunk_quality_audit_service import (
    analyze_book_chunks,
    analyze_chunk_quality,
    detect_repeated_margin_signatures,
    should_skip_for_ingestion,
)


def test_detects_reference_like_chunk():
    analysis = analyze_chunk_quality(
        "Turner, B. S. (1990) Theories of Modernity. London: Sage. "
        "Turner, B. S. (1992) Max Weber. London: Routledge."
    )
    assert analysis["bibliography_like"] is True


def test_detects_broken_mid_sentence_chunk():
    analysis = analyze_chunk_quality(
        "lukta birakan Tannnnn her seyin onceden duzenlendigi gorusu lehinde de pasajlara rastlanabilir."
    )
    assert analysis["broken_start"] is True


def test_skip_for_ingestion_rejects_toc_like_chunk():
    skip, analysis = should_skip_for_ingestion(
        "İÇİNDEKİLER\n1. Giriş ........ 7\n2. Yöntem ........ 12\n3. Sonuç ........ 44"
    )
    assert skip is True
    assert analysis["toc_like"] is True


def test_skip_for_ingestion_rejects_front_matter_heading():
    skip, analysis = should_skip_for_ingestion(
        "SUNUŞ",
        page_number=4,
    )
    assert skip is True
    assert analysis["front_matter_like"] is True


def test_skip_for_ingestion_rejects_orphan_fragment_on_early_pages():
    skip, analysis = should_skip_for_ingestion(
        "maktı. İkiyüz yıldır sürdürülen batılılaşma hareketleri içinde vukubulan iktisadî değişmelerin etkisi büyüktür",
        page_number=5,
    )
    assert skip is True
    assert analysis["orphan_fragment"] is True


def test_skip_for_ingestion_rejects_catalog_like_front_matter():
    skip, analysis = should_skip_for_ingestion(
        "2- Jean-Luc Nancy / Demokrasinin Hakikati 3- Jean-François Lyotard / Pagan Eğitimler",
        page_number=5,
    )
    assert skip is True
    assert analysis["catalog_like"] is True


def test_detect_repeated_margin_signatures():
    pages = [
        {"page_num": 1, "lines": [{"text": "Islam Felsefesi Uzerine - Ahmet Arslan"}, {"text": "Govde satiri 1"}]},
        {"page_num": 2, "lines": [{"text": "Islam Felsefesi Uzerine - Ahmet Arslan"}, {"text": "Govde satiri 2"}]},
        {"page_num": 3, "lines": [{"text": "Islam Felsefesi Uzerine - Ahmet Arslan"}, {"text": "Govde satiri 3"}]},
    ]
    repeated = detect_repeated_margin_signatures(pages, sample_depth=1)
    assert repeated


def test_book_audit_reports_problem_counts():
    report = analyze_book_chunks(
        [
            {"id": 1, "page_number": 10, "content_chunk": "ve bu nedenle ortadan baslayan bir cumle gibi gorunuyor"},
            {"id": 2, "page_number": 59, "content_chunk": "Kaynakça\nTurner, B. S. (1990) London: Sage."},
        ],
        title="Klasik Sosyoloji",
        author="Bryan S. Turner",
    )
    assert report["broken_start_count"] >= 1
    assert report["bibliography_like_count"] >= 1
