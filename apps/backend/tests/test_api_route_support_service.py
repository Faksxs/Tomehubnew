import unittest
from types import SimpleNamespace

from fastapi import BackgroundTasks

from services.api_route_support_service import execute_chat_request, execute_search_request


class ApiRouteSupportCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_chat_request_defaults_missing_domain_mode_to_auto(self):
        captured: dict[str, str] = {}

        def generate_answer(**kwargs):
            captured["domain_mode"] = kwargs.get("domain_mode")
            return "ok", [], {}

        result = await execute_chat_request(
            chat_request=SimpleNamespace(
                message="namazla ilgili hadisleri ara",
                session_id=None,
                book_id=None,
                context_book_id=None,
                resource_type=None,
                scope_mode="AUTO",
                compare_mode="EXPLICIT_ONLY",
                target_book_ids=None,
                mode="STANDARD",
                limit=20,
                offset=0,
            ),
            firebase_uid="u1",
            background_tasks=BackgroundTasks(),
            generate_answer_fn=generate_answer,
            get_rag_context_fn=lambda *args, **kwargs: None,
            generate_evaluated_answer_fn=lambda **kwargs: {},
            create_session_fn=lambda firebase_uid, title: 101,
            add_message_fn=lambda *args, **kwargs: None,
            get_session_context_fn=lambda session_id: {
                "recent_messages": [],
                "summary": "",
                "conversation_state_json": "",
            },
            summarize_session_history_fn=lambda session_id: None,
            get_memory_context_snippet_fn=lambda firebase_uid: "",
            refresh_memory_profile_fn=lambda firebase_uid: None,
        )

        self.assertEqual(captured["domain_mode"], "AUTO")
        self.assertEqual(result["metadata"]["requested_domain_mode"], "AUTO")
        self.assertEqual(result["session_id"], 101)

    async def test_execute_chat_request_explorer_omits_unsupported_domain_mode_kwarg(self):
        captured: dict[str, object] = {}

        def get_rag_context(question, firebase_uid, context_book_id=None, chat_history=None, mode="STANDARD", resource_type=None, scope_mode="GLOBAL", apply_scope_policy=False, compare_mode=None, target_book_ids=None, limit=None, offset=0):
            captured["question"] = question
            captured["has_domain_mode"] = False
            return {
                "chunks": [],
                "confidence": 0.0,
                "metadata": {},
            }

        async def generate_evaluated_answer(**kwargs):
            return {
                "final_answer": "ok",
                "metadata": {
                    "history": [],
                    "used_chunks": [],
                },
            }

        result = await execute_chat_request(
            chat_request=SimpleNamespace(
                message="explorer test",
                session_id=None,
                book_id=None,
                context_book_id=None,
                resource_type=None,
                scope_mode="AUTO",
                compare_mode="EXPLICIT_ONLY",
                target_book_ids=None,
                mode="EXPLORER",
                limit=20,
                offset=0,
            ),
            firebase_uid="u1",
            background_tasks=BackgroundTasks(),
            generate_answer_fn=lambda **kwargs: ("unused", [], {}),
            get_rag_context_fn=get_rag_context,
            generate_evaluated_answer_fn=generate_evaluated_answer,
            create_session_fn=lambda firebase_uid, title: 202,
            add_message_fn=lambda *args, **kwargs: None,
            get_session_context_fn=lambda session_id: {
                "recent_messages": [],
                "summary": "",
                "conversation_state_json": "",
            },
            summarize_session_history_fn=lambda session_id: None,
            get_memory_context_snippet_fn=lambda firebase_uid: "",
            refresh_memory_profile_fn=lambda firebase_uid: None,
        )

        self.assertEqual(captured["question"], "explorer test")
        self.assertEqual(result["metadata"]["requested_domain_mode"], "AUTO")
        self.assertEqual(result["session_id"], 202)

    async def test_execute_search_request_defaults_missing_domain_mode_to_auto(self):
        captured: dict[str, str] = {}

        def generate_answer(**kwargs):
            captured["domain_mode"] = kwargs.get("domain_mode")
            return "ok", [], {}

        result = await execute_search_request(
            search_request=SimpleNamespace(
                question="hadis ara",
                include_private_notes=False,
                visibility_scope="default",
                book_id=None,
                context_book_id=None,
                mode="EXPLORER",
                scope_mode="AUTO",
                resource_type=None,
                compare_mode="EXPLICIT_ONLY",
                target_book_ids=None,
                limit=20,
                offset=0,
                content_type=None,
                ingestion_type=None,
            ),
            firebase_uid="u1",
            generate_answer_fn=generate_answer,
        )

        self.assertEqual(captured["domain_mode"], "AUTO")
        self.assertEqual(result["metadata"]["requested_domain_mode"], "AUTO")


if __name__ == "__main__":
    unittest.main()
