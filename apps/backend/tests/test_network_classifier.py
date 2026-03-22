import unittest

from services.epistemic_service import get_prompt_for_mode
from services.network_classifier import classify_network_status


class NetworkClassifierTests(unittest.TestCase):
    def test_primary_religious_external_evidence_counts_as_in_network(self):
        chunks = [
            {
                "content_chunk": "Namazla ilgili hadis ve cemaatle namaz vurgusu.",
                "answerability_score": 1.1,
                "source_type": "ISLAMIC_EXTERNAL",
                "religious_source_kind": "HADITH",
            },
            {
                "content_chunk": "Namaz hadisi baglami ve rivayet.",
                "answerability_score": 1.0,
                "source_type": "ISLAMIC_EXTERNAL",
                "religious_source_kind": "HADITH",
            },
        ]

        result = classify_network_status("namazla ilgili hadisleri getir", chunks)

        self.assertEqual(result["status"], "IN_NETWORK")
        self.assertTrue(result["metrics"]["has_primary_religious_evidence"])

    def test_religious_prompt_does_not_force_missing_notes_warning_when_external_evidence_exists(self):
        context = (
            "### KAYNAK DOKUMANLAR\n"
            "[Tip: ISLAMIC_EXTERNAL | Provider: HADEETHENC | Religious: HADITH | Ref: 123]\n"
            "ICERIK: Namazla ilgili hadis.\n"
        )

        prompt = get_prompt_for_mode(
            "EXPLORER",
            context,
            "namazla ilgili hadisleri getir",
            confidence_score=1.2,
            network_status="OUT_OF_NETWORK",
            domain_mode="RELIGIOUS",
        )

        self.assertIn("Ayet/hadis gibi", prompt)
        self.assertNotIn("UYARI:", prompt)


if __name__ == "__main__":
    unittest.main()
