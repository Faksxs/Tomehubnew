import unittest

from services.search_system.semantic_router import SemanticRouter


class TestSemanticRouterModes(unittest.TestCase):
    def setUp(self):
        self.router = SemanticRouter()

    def test_direct_intent_routes_fast_exact(self):
        decision = self.router.route("hangi sayfa", intent="DIRECT")
        self.assertEqual(decision.retrieval_mode, "fast_exact")
        self.assertEqual(decision.selected_buckets, ["exact", "lemma"])

    def test_conceptual_hint_routes_semantic_focus(self):
        decision = self.router.route("vicdan nedir", intent="SYNTHESIS")
        self.assertEqual(decision.retrieval_mode, "semantic_focus")
        self.assertEqual(decision.selected_buckets, ["lemma", "semantic", "exact"])

    def test_short_query_routes_balanced(self):
        decision = self.router.route("vicdan", intent="SYNTHESIS")
        self.assertEqual(decision.retrieval_mode, "balanced")
        self.assertEqual(decision.selected_buckets, ["exact", "lemma", "semantic"])

    def test_default_mode_can_be_forced(self):
        decision = self.router.route("tamamen rastgele sorgu", intent="SYNTHESIS", default_mode="fast_exact")
        self.assertEqual(decision.retrieval_mode, "fast_exact")
        self.assertEqual(decision.selected_buckets, ["exact", "lemma"])


if __name__ == "__main__":
    unittest.main()
