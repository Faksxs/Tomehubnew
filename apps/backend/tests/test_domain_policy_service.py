import unittest

from services.domain_policy_service import (
    DOMAIN_MODE_ACADEMIC,
    DOMAIN_MODE_AUTO,
    DOMAIN_MODE_CULTURE_HISTORY,
    DOMAIN_MODE_LITERARY,
    DOMAIN_MODE_RELIGIOUS,
    domain_allows_provider_group,
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


if __name__ == "__main__":
    unittest.main()
