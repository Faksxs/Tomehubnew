# TomeHub Cleanup and Optimization Execution Report (2026-02-12)

## Scope
- Runtime + Assets + Docs
- Archive-first for medium-risk items
- No business-logic or API contract change

## Applied Changes

### 1) Low-risk cleanup (removed)
- Removed backend generated artifact files (logs/outputs/lists) from `apps/backend/`:
  - `audit_result.txt`, `book_details_output.txt`, `book_list.txt`, `books_output.txt`
  - `cleanup_log*.txt`, `cols*.txt`, `content_columns*.txt`, `context_out.txt`
  - `debug_output*.txt`, `debug_title.txt`, `demo_*output*.txt`, `diag_result.txt`
  - `hayatin_analami_search.txt`, `log_dump.txt`, `output.txt`, `pdf_list.txt`, `pdf_titles.txt`
  - `routes.txt`, `test_layer3_output.txt`, `titles_debug.txt`, `titles_list.txt`, `uids_list.txt`
  - `verification_output.txt`, `verify_output.txt`
- Removed unused heavy frontend assets:
  - `apps/frontend/src/assets/logo.png`
  - `apps/frontend/src/assets/logo_v1_measured.png`
  - `apps/frontend/src/assets/logo_v2.png`
  - `apps/frontend/src/assets/logo_v3.png`
  - `apps/frontend/src/assets/logo_v4.png`
  - `apps/frontend/src/assets/logo_v6.png`
  - `apps/frontend/public/logo_v6.png`
  - `apps/frontend/public/favicon.png`

### 2) Archive-first moves (medium-risk)
- Moved backend root debug scripts to:
  - `apps/backend/scripts/archive/root_debug/`
- Moved backend root ad-hoc test scripts to:
  - `apps/backend/scripts/archive/root_tests/`
- Moved legacy search strategy variants to:
  - `apps/backend/services/search_system/_deprecated/`
  - Added `apps/backend/services/search_system/_deprecated/__init__.py`
- Updated archived debug script import:
  - `debug_strategies_live.py` now imports from `_deprecated.strategies_final`

### 3) Docs archive + redirects
- Archived legacy Flask guides to:
  - `documentation/legacy/flask_guides/`
- Added short redirect notes at original paths:
  - `documentation/guides/API_GUIDE.md`
  - `documentation/guides/INGESTION_GUIDE.md`
  - `documentation/guides/PDF_SERVICE_GUIDE.md`
  - `documentation/guides/SEARCH_SERVICE_GUIDE.md`
  - `docs/FRONTEND_INTEGRATION.md`

### 4) Dependency and config cleanup
- Frontend (`apps/frontend/package.json`):
  - Removed: `@google/genai`, `@google/generative-ai`, `@dnd-kit/sortable`
  - Added direct dependency: `@dnd-kit/utilities`
  - Updated `apps/frontend/package-lock.json`
- Functions (`functions/package.json`):
  - Removed: `axios`
  - Updated `functions/package-lock.json`
- Docker compose (`infra/docker-compose.yml`):
  - Renamed `FLASK_ENV` -> `APP_ENV`
  - Renamed `FLASK_DEBUG` -> `APP_DEBUG`
- Git ignore hardening (`.gitignore`):
  - Added patterns for backend generated diagnostics artifacts

### 5) Safe runtime log normalization
- Replaced runtime `print()` usage with structured logging in:
  - `apps/backend/routes/flow_routes.py`
  - `apps/backend/services/analytics_service.py`
  - `apps/backend/services/smart_search_service.py`
  - `apps/backend/services/search_service.py` (runtime path only; interactive `__main__` kept)
  - `apps/backend/services/ingestion_service.py`
  - `apps/backend/services/pdf_service.py`
- Added log controls:
  - `LOG_LEVEL` and `DEBUG_VERBOSE_PIPELINE` in `apps/backend/config.py`
  - Added same keys in `apps/backend/.env.example`
  - `apps/backend/app.py` now reads logger level from `settings.LOG_LEVEL`

## Validation Results
- Backend syntax check:
  - `python -m py_compile ...` on modified core modules: PASS
- Frontend build:
  - `npm run build`: PASS
- Backend fast unit subset:
  - `python -m unittest tests/test_request_models_validation.py tests/test_safe_read_clob.py tests/test_llm_client.py tests/test_flow_content_limit.py`: PASS (22 tests)
- Functions dependency integrity:
  - `npm ls --depth=0`: PASS

## Safety Notes
- Runtime API schemas/endpoints were not changed.
- Core layer boundaries and business logic were preserved.
- Archive-first policy applied for medium-risk items.

## Rollback Notes
- File moves are git renames; rollback is straightforward with `git restore --staged --worktree <path>` for selected paths.
- Dependency changes can be reverted with package.json/package-lock restore.
- Logger normalization is isolated to explicit files listed above.
