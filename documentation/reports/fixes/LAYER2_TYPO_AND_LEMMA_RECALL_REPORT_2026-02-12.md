# Layer-2 Typo and Lemma Recall Report (2026-02-12)

## 1. Problem Summary
Layer-2 (`/api/smart-search`) had two recurring quality failures:
- Minor typo queries (ex: `yonetm`, `onlarn`) were dropping into semantic-heavy results too early.
- After direct lexical hits, root-close lexical recall was not consistently recovered before semantic tail.

## 2. Root Cause Findings
- Smart Search always runs with `result_mix_policy="lexical_then_semantic_tail"` and semantic tail cap defaults from config.
- Query expansion does not run for single-token queries, so typo rescue was missing on this path.
- Spell checker existed but was only used in Judge/OCR checks, not in Smart Search retrieval orchestration.
- In low lexical cases, semantic bucket could dominate candidate pool and introduce unrelated noise.

## 3. Implemented Changes
### 3.1 Typo Rescue in Orchestrator
File: `apps/backend/services/search_system/orchestrator.py`
- Added typo rescue gate when initial lexical raw count is low (`<=2`).
- Applies deterministic local correction via `get_spell_checker().correct(query)`.
- If corrected query differs, reruns lexical strategies once (exact + lemma) and merges results before semantic tail.

### 3.2 Lemma-Seed Exact Fallback
File: `apps/backend/services/search_system/orchestrator.py`
- If lemma bucket remains empty, derives 1-2 filtered lemma seeds from original/corrected query.
- Runs exact search on those seeds and injects results with `match_type='exact_lemma_seed'`.

### 3.3 Dynamic Semantic Tail for Single-Token Queries
File: `apps/backend/services/search_system/orchestrator.py`
- New policy for single-token queries based on lexical total:
  - `>30 -> 2`
  - `20-30 -> 3`
  - `10-19 -> 4`
  - `<10 -> 5`
- Multi-token behavior remains default (`SEARCH_SMART_SEMANTIC_TAIL_CAP`).

### 3.4 Feature Flags
Files:
- `apps/backend/config.py`
- `apps/backend/.env.example`

Added flags:
- `SEARCH_TYPO_RESCUE_ENABLED=true`
- `SEARCH_LEMMA_SEED_FALLBACK_ENABLED=true`
- `SEARCH_DYNAMIC_SINGLE_TOKEN_SEMANTIC_CAP_ENABLED=true`

### 3.5 Metadata Additions (Non-breaking)
File: `apps/backend/services/search_system/orchestrator.py`

`/api/smart-search` metadata now includes:
- `query_original`
- `query_corrected`
- `query_correction_applied`
- `typo_rescue_applied`
- `lemma_seed_fallback_applied`
- `semantic_tail_cap_effective`
- `semantic_tail_policy`

Plus retrieval diagnostics for initial vs post-rescue lexical counts.

## 4. Tests Added
Files:
- `apps/backend/tests/test_search_typo_rescue.py`
- `apps/backend/tests/test_search_semantic_tail_policy.py`

Coverage:
- Typo rescue trigger and non-trigger cases.
- Dynamic semantic tail cap band behavior.
- Single-token dynamic policy vs multi-token default policy.

## 5. Latency Risk Assessment
- Typo rescue adds at most one extra lexical pass only under low-lexical conditions.
- Spell correction overhead is local and low-cost (sub-ms scale per query after load).
- Dynamic single-token semantic cap reduces semantic tail size in high-lexical scenarios, lowering noise and often reducing latency.

## 6. Acceptance Criteria (Target)
- Typo queries improve lexical-first recall in first page results.
- Single-token semantic noise reduces without harming lexical ordering.
- `/api/smart-search` p95 latency increase remains <= 10%.
