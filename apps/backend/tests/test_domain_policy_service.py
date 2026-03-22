import unittest

from services.domain_policy_service import (
    DOMAIN_MODE_ACADEMIC,
    DOMAIN_MODE_AUTO,
    DOMAIN_MODE_CULTURE_HISTORY,
    DOMAIN_MODE_LITERARY,
    DOMAIN_MODE_RELIGIOUS,
    domain_allows_provider_group,
    infer_literary_query_type,
    infer_religious_query_type,
    resolve_explorer_query_profile,
    resolve_domain_mode,
)


class DomainPolicyServiceTests(unittest.TestCase):
    def test_explicit_override_wins(self):
        resolved = resolve_domain_mode(
            "poem and imagery",
            requested_domain_mode=DOMAIN_MODE_RELIGIOUS,
            chat_history=[{"content": "paper methodology"}],
        )

        self.assertEqual(resolved["resolved_domain_mode"], DOMAIN_MODE_RELIGIOUS)
        self.assertEqual(resolved["domain_reason"], "user_override")

    def test_auto_detects_religious(self):
        resolved = resolve_domain_mode("Bakara 2:255 ayeti ne diyor?")
        self.assertEqual(resolved["resolved_domain_mode"], DOMAIN_MODE_RELIGIOUS)

    def test_auto_detects_academic(self):
        resolved = resolve_domain_mode("literature review and citation analysis for this paper")
        self.assertEqual(resolved["resolved_domain_mode"], DOMAIN_MODE_ACADEMIC)

    def test_auto_detects_literary(self):
        resolved = resolve_domain_mode("poem imagery and metaphor in this stanza")
        self.assertEqual(resolved["resolved_domain_mode"], DOMAIN_MODE_LITERARY)

    def test_auto_detects_culture_history(self):
        resolved = resolve_domain_mode("historical archive and museum context for this empire")
        self.assertEqual(resolved["resolved_domain_mode"], DOMAIN_MODE_CULTURE_HISTORY)

    def test_recent_history_can_drive_auto_resolution(self):
        resolved = resolve_domain_mode(
            "bunu biraz daha acar misin",
            chat_history=[
                {"content": "this paper's methodology and citation network"},
                {"content": "compare the literature review"},
            ],
        )
        self.assertEqual(resolved["resolved_domain_mode"], DOMAIN_MODE_ACADEMIC)
        self.assertEqual(resolved["domain_reason"], "history_inference")

    def test_provider_group_gating(self):
        self.assertTrue(domain_allows_provider_group(DOMAIN_MODE_ACADEMIC, "EXTERNAL_KB"))
        self.assertFalse(domain_allows_provider_group(DOMAIN_MODE_ACADEMIC, "ISLAMIC_API"))
        self.assertTrue(domain_allows_provider_group(DOMAIN_MODE_RELIGIOUS, "ISLAMIC_API"))
        self.assertFalse(domain_allows_provider_group(DOMAIN_MODE_RELIGIOUS, "EXTERNAL_KB"))
        self.assertTrue(domain_allows_provider_group(DOMAIN_MODE_AUTO, "EXTERNAL_KB"))

    def test_infer_religious_query_type_distinguishes_exact_and_topical(self):
        self.assertEqual(infer_religious_query_type("Bakara 2:255 ayeti ne diyor?"), "EXACT_QURAN_VERSE")
        self.assertEqual(infer_religious_query_type("namaz hadislerini getir"), "TOPICAL_HADITH")

    def test_infer_literary_query_type_distinguishes_close_reading_and_author_context(self):
        self.assertEqual(
            infer_literary_query_type("poem imagery and metaphor in this stanza"),
            "CLOSE_READING",
        )
        self.assertEqual(
            infer_literary_query_type("Shakespeare author background and biography"),
            "AUTHOR_CONTEXT",
        )

    def test_resolved_auto_profiles_include_confidence_band_and_secondary_mode(self):
        resolved = resolve_domain_mode("research paper history of Ottoman poetry")
        profile = resolve_explorer_query_profile(
            "research paper history of Ottoman poetry",
            resolved_domain_mode=resolved["resolved_domain_mode"],
            domain_confidence=resolved["domain_confidence"],
            requested_domain_mode=DOMAIN_MODE_AUTO,
            domain_reason=resolved["domain_reason"],
            secondary_domain_mode=resolved.get("secondary_domain_mode"),
        )

        self.assertIn(profile["auto_confidence_band"], {"high", "medium", "low"})
        self.assertEqual(profile["resolved_domain_mode"], resolved["resolved_domain_mode"])
        self.assertEqual(profile["secondary_domain_mode"], resolved.get("secondary_domain_mode"))

    def test_religious_exact_profile_prioritizes_islamic_external(self):
        profile = resolve_explorer_query_profile(
            "Bakara 2:255 ayeti ne diyor?",
            resolved_domain_mode=DOMAIN_MODE_RELIGIOUS,
            domain_confidence=0.93,
            requested_domain_mode=DOMAIN_MODE_AUTO,
            domain_reason="keyword_inference",
        )

        self.assertEqual(profile["religious_query_type"], "EXACT_QURAN_VERSE")
        self.assertGreaterEqual(profile["islamic_external_limit"], 4)
        self.assertEqual(profile["primary_source_types"], ["ISLAMIC_EXTERNAL"])

    def test_literary_author_context_profile_expands_external_context_budget(self):
        profile = resolve_explorer_query_profile(
            "Shakespeare author background and biography",
            resolved_domain_mode=DOMAIN_MODE_LITERARY,
            domain_confidence=0.88,
            requested_domain_mode=DOMAIN_MODE_AUTO,
            domain_reason="keyword_inference",
        )

        self.assertEqual(profile["literary_query_type"], "AUTHOR_CONTEXT")
        self.assertGreaterEqual(profile["direct_external_limit"], 4)
        self.assertGreater(profile["provider_multipliers"]["GOOGLE_BOOKS"], 1.0)


if __name__ == "__main__":
    unittest.main()
