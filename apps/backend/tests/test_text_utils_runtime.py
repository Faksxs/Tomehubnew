import unittest
from unittest.mock import patch

import zeyrek.morphology as zeyrek_morphology

from utils import text_utils


class TextUtilsRuntimeTests(unittest.TestCase):
    def test_zeyrek_tokenizer_patch_does_not_require_nltk_punkt(self):
        with patch.object(
            zeyrek_morphology,
            "word_tokenize",
            side_effect=LookupError("punkt_tab missing"),
        ):
            tokens = text_utils._zeyrek_regex_tokenize("Kader ve özgürlük")

        self.assertEqual(tokens, ["Kader", "ve", "özgürlük"])

    def test_get_lemmas_survives_missing_word_tokenize_runtime(self):
        if text_utils._analyzer is None:
            self.skipTest("Zeyrek analyzer unavailable")

        with patch.object(
            zeyrek_morphology,
            "word_tokenize",
            side_effect=LookupError("punkt_tab missing"),
        ):
            lemmas = text_utils.get_lemmas("Kader ve özgürlük")

        self.assertTrue(lemmas)


if __name__ == "__main__":
    unittest.main()
