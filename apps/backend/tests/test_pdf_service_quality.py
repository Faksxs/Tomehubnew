from services.pdf_service import ChunkReconstructor, calculate_sis


def test_chunk_reconstructor_merges_page_break_continuation():
    reconstructor = ChunkReconstructor()
    reconstructor.add(
        {"text": "Bu paragraf bir sonraki satirda devam eden", "page_num": 10, "confidence": 0.99, "line_index": 1}
    )
    reconstructor.add(
        {"text": "ve daha sonra cumleye donusen bir parca.", "page_num": 10, "confidence": 0.97, "line_index": 2}
    )
    reconstructor.flush()

    assert len(reconstructor.final_chunks) == 1
    assert "cumleye donusen" in reconstructor.final_chunks[0]["text"]


def test_calculate_sis_quarantines_bibliography():
    sis = calculate_sis("Kaynakça\nTurner, B. S. (1990) London: Sage.\nTurner, B. S. (1992) London: Routledge.")
    assert sis["decision"] == "QUARANTINE"
