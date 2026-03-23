import unittest

from services.search_diagnostics_service import enrich_search_metadata


class TestSearchDiagnosticTrace(unittest.TestCase):
    def test_enrich_search_metadata_builds_standard_trace_and_planes(self):
        metadata = {
            "status": "healthy",
            "retrieval_mode": "balanced",
            "selected_buckets": ["exact", "lemma", "semantic"],
            "retrieval_steps": {"exact": 4, "lemma": 2, "semantic": 3},
            "typo_rescue_applied": True,
            "rerank_top1_changed": False,
            "graph_candidates_count": 1,
            "external_graph_candidates_count": 2,
            "index_freshness_state": "vector_ready",
        }
        results = [
            {"source_type": "HIGHLIGHT"},
            {"source_type": "BOOK"},
            {"source_type": "HIGHLIGHT"},
            {"source_type": "ARTICLE"},
        ]

        enriched = enrich_search_metadata(
            metadata,
            endpoint="/api/search",
            query="adalet nedir",
            intent="SYNTHESIS",
            results=results,
            answer=(
                "Bu cevap yeterince uzun ve kaynaklarla destekli. "
                "Metin birden fazla kanıt sinyali içeriyor ve kısa cevap eşiğinin üstünde kalıyor. "
                "Bu yüzden generation plane sağlıklı görünmeli."
            ),
            sources=results,
        )

        self.assertEqual(enriched["diagnostic_trace_v1"]["endpoint"], "/api/search")
        self.assertEqual(enriched["diagnostic_trace_v1"]["retrieval_counts"]["exact"], 4)
        self.assertEqual(enriched["diagnostic_trace_v1"]["retrieval_counts"]["lemma"], 2)
        self.assertEqual(enriched["diagnostic_trace_v1"]["retrieval_counts"]["semantic"], 3)
        self.assertEqual(enriched["diagnostic_trace_v1"]["top_source_types"], ["HIGHLIGHT", "BOOK", "ARTICLE"])
        self.assertIn('endpoint=/api/search', enriched["diagnostic_trace_line"])
        self.assertEqual(enriched["retrieval_failure_plane"], "evidence_ready")
        self.assertEqual(enriched["generation_failure_plane"], "answer_ready")
        self.assertEqual(enriched["failure_plane"], "none")
        self.assertEqual(enriched["freshness_plane"], "ready")
        self.assertEqual(enriched["search_quality_plane"], "healthy")

    def test_enrich_search_metadata_separates_retrieval_and_generation_failures(self):
        retrieval_missing = enrich_search_metadata(
            {
                "status": "healthy",
                "retrieval_mode": "fast_exact",
                "retrieval_steps": {"exact": 0, "lemma": 0, "semantic": 0},
                "graph_candidates_count": 0,
                "external_graph_candidates_count": 0,
            },
            endpoint="/api/search",
            query="kaynak yok",
            intent="DIRECT",
            results=[],
            answer="",
            sources=[],
        )
        self.assertEqual(retrieval_missing["retrieval_failure_plane"], "no_evidence")
        self.assertEqual(retrieval_missing["generation_failure_plane"], "empty_answer")
        self.assertEqual(retrieval_missing["failure_plane"], "mixed")
        self.assertEqual(retrieval_missing["freshness_plane"], "not_checked")
        self.assertEqual(retrieval_missing["search_quality_plane"], "needs_attention")

        generation_only = enrich_search_metadata(
            {
                "status": "error",
                "retrieval_mode": "balanced",
                "retrieval_steps": {"exact": 3, "lemma": 1, "semantic": 0},
                "graph_candidates_count": 0,
                "external_graph_candidates_count": 0,
            },
            endpoint="/api/search",
            query="cevap bozuldu",
            intent="SYNTHESIS",
            results=[{"source_type": "BOOK"}, {"source_type": "ARTICLE"}, {"source_type": "HIGHLIGHT"}],
            answer="teknik hata",
            sources=[{"source_type": "BOOK"}, {"source_type": "ARTICLE"}, {"source_type": "HIGHLIGHT"}],
        )
        self.assertEqual(generation_only["retrieval_failure_plane"], "evidence_ready")
        self.assertEqual(generation_only["generation_failure_plane"], "generation_error")
        self.assertEqual(generation_only["failure_plane"], "generation")


if __name__ == "__main__":
    unittest.main()
