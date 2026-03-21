import unittest
from types import SimpleNamespace

from fastapi import BackgroundTasks

from services.api_route_support_service import execute_chat_request, execute_search_request


class ApiRouteSupportCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_chat_request_defaults_missing_domain_mode_to_auto(self):
        captured: dict[str, str] = {}

        def generate_answer(*args):
            captured["domain_mode"] = args[-1]
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

    async def test_execute_search_request_defaults_missing_domain_mode_to_auto(self):
        captured: dict[str, str] = {}

        def generate_answer(*args):
            captured["domain_mode"] = args[-1]
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
