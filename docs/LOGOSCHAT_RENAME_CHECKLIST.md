# LogosChat Rename Checklist

This checklist covers post-rename validation for `LagosChat -> LogosChat`.

## Scope Guardrails
- Keep technical identifiers unchanged:
  - `RAG_SEARCH`
  - `/api/chat`
  - Existing request/response schemas
- Change only user-facing/product wording and developer-facing descriptions.

## Runtime / Config Validation
- No env key rename is required for this change.
- Verify Vercel/Runtime env keys do not contain `LAGOS`/`LOGOS` naming dependencies.

## Build and Smoke
1. Frontend build
   - `cd apps/frontend`
   - `npm run build`
2. Backend startup syntax check
   - `cd apps/backend`
   - `python -m py_compile app.py`
3. Route behavior check
   - Confirm `/api/chat` endpoint is still reachable and unchanged by contract.

## String Integrity
1. Codebase grep
   - `rg -n "LagosChat|Lagos Chat"`
2. Expected result
   - No active code/docs references remain (archived logs/debug dumps can be excluded).

## DB Safe Rename Script
- Script path: `apps/backend/scripts/rename_lagoschat_to_logoschat.py`

### Dry-run
- `cd apps/backend`
- `python scripts/rename_lagoschat_to_logoschat.py`
- Expected: prints candidate columns and either:
  - `No matches found. 0 updates.`, or
  - per-column match counts.

### Apply
- `cd apps/backend`
- `python scripts/rename_lagoschat_to_logoschat.py --apply`
- Expected:
  - Transactional update report with per-column updated rows.
  - Re-running dry-run should produce `0 updates` (idempotent behavior).
