import unittest

from services.search_system.strategies import (
    _count_lemma_stem_hits,
    _contains_inner_substring_only,
    _contains_exact_term_boundary,
    _contains_lemma_stem_boundary,
)


class TestSearchExactBoundary(unittest.TestCase):
    def test_does_not_match_inside_longer_word(self):
        text = "Medeniyet sehir kokunden gelir."
        self.assertFalse(_contains_exact_term_boundary(text, "niyet"))

    def test_matches_standalone_word(self):
        text = "Insan iyi niyet ile hareket eder."
        self.assertTrue(_contains_exact_term_boundary(text, "niyet"))

    def test_matches_with_turkish_deaccent(self):
        text = "YONETIM bir sanattir."
        self.assertTrue(_contains_exact_term_boundary(text, "yonetim"))

    def test_matches_phrase_boundary(self):
        text = "Bu metinde iyi-niyet kavrami tartisiliyor."
        self.assertTrue(_contains_exact_term_boundary(text, "iyi niyet"))

    def test_lemma_stem_matches_valid_derivation(self):
        text = "Insan iyi niyetli gorunmeye calisiyor."
        self.assertTrue(_contains_lemma_stem_boundary(text, "niyet"))

    def test_lemma_stem_rejects_inner_word_match(self):
        text = "Medeniyet tarihi farkli bir kavramdir."
        self.assertFalse(_contains_lemma_stem_boundary(text, "niyet"))

    def test_lemma_stem_hit_count(self):
        text = "Niyet iyi niyetli davranista niyetler etkili olur."
        self.assertGreaterEqual(_count_lemma_stem_hits(text, ["niyet"]), 3)

    def test_inner_substring_only_detection(self):
        self.assertTrue(_contains_inner_substring_only("Medeniyet Tarihi", "niyet"))
        self.assertFalse(_contains_inner_substring_only("Niyet Uzerine", "niyet"))


if __name__ == "__main__":
    unittest.main()
