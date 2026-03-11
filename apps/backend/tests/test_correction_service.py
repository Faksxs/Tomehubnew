from services.correction_service import LinguisticCorrectionService


def test_correction_service_applies_targeted_fix():
    service = LinguisticCorrectionService()
    repaired = service.fix_text("gOn bir ornektir.")
    assert "g\u00fcn" in repaired


def test_correction_service_rejects_high_delta_rewrite():
    service = LinguisticCorrectionService()
    original = "~ ~ ~ ~ ~ ~ ~ ~ ~ ~"
    repaired = service.fix_text(original)
    assert repaired == original
