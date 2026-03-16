from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "reembed_embeddings_inplace.py"
)
SPEC = importlib.util.spec_from_file_location("reembed_embeddings_inplace", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_estimate_tokens_from_chars_rounds_up():
    assert MODULE._estimate_tokens_from_chars(0) == 0
    assert MODULE._estimate_tokens_from_chars(1) == 1
    assert MODULE._estimate_tokens_from_chars(4) == 1
    assert MODULE._estimate_tokens_from_chars(5) == 2


def test_normalize_scope_all_returns_content_then_concepts():
    scopes = MODULE._normalize_scope("all")
    assert [item.scope for item in scopes] == ["content", "concepts"]


def test_checkpoint_roundtrip(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "checkpoint.json"
    monkeypatch.setattr(MODULE, "CHECKPOINT_PATH", str(checkpoint_path))

    payload = {
        "updated_at": None,
        "content": {"last_id": 10, "processed": 5, "batches": 1},
        "concepts": {"last_id": 20, "processed": 7, "batches": 2},
    }
    MODULE._save_checkpoint(payload)
    loaded = MODULE._load_checkpoint()

    assert loaded["content"]["last_id"] == 10
    assert loaded["concepts"]["processed"] == 7
    assert loaded["updated_at"]


def test_rate_window_throttle_accepts_small_budget():
    throttle = MODULE.RateWindowThrottle(limit_per_minute=10)
    waited = throttle.wait_for_budget(3)
    assert waited >= 0.0


def test_direct_batch_embeddings_raises_on_count_mismatch(monkeypatch):
    monkeypatch.setattr(MODULE, "get_model_for_tier", lambda _: "gemini-embedding-2-preview")
    monkeypatch.setattr(MODULE, "embed_contents", lambda **kwargs: [[0.1, 0.2]])
    try:
        MODULE._direct_batch_embeddings(["a", "b"])
    except RuntimeError as exc:
        assert "count mismatch" in str(exc)
    else:
        raise AssertionError("Expected count mismatch runtime error")
