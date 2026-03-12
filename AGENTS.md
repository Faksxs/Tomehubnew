# AGENTS

<skills_system priority="1">

## Available Skills

<!-- SKILLS_TABLE_START -->
<usage>
When users ask you to perform tasks, check if any of the available skills below can help complete the task more effectively. Skills provide specialized capabilities and domain knowledge.

How to use skills:
- Invoke: `npx openskills read <skill-name>` (run in your shell)
  - For multiple: `npx openskills read skill-one,skill-two`
- The skill content will load with detailed instructions on how to complete the task
- Base directory provided in output for resolving bundled resources (references/, scripts/, assets/)

Usage notes:
- Only use skills listed in <available_skills> below
- Do not invoke a skill that is already loaded in your context
- Each skill invocation is stateless
</usage>

<available_skills>

<skill>
<name>api</name>
<description>FastAPI endpoint, route, request-response model, and service-layer implementation guidance for TomeHub backend APIs, ingestion endpoints, and AI-related API flows.</description>
<location>project</location>
</skill>

<skill>
<name>architect</name>
<description>Architecture decision support for TomeHub systems including service boundaries, scaling strategy, and maintainable design tradeoffs.</description>
<location>project</location>
</skill>

<skill>
<name>cloud</name>
<description>Firebase and cloud-function implementation guidance focused on secure, low-latency, idempotent serverless behavior.</description>
<location>project</location>
</skill>

<skill>
<name>data</name>
<description>Data and retrieval guidance for TomeHub RAG, ingestion pipelines, indexing strategy, and query performance.</description>
<location>project</location>
</skill>

<skill>
<name>guard</name>
<description>Security and authorization guardrails for authentication, permissions, tokens, and sensitive operations.</description>
<location>project</location>
</skill>

<skill>
<name>tomehub-api-release-gate</name>
<description>Enforce pre-release API safety checks for TomeHub backend changes with contract validation, regression checks, and rollout readiness criteria.</description>
<location>project</location>
</skill>

<skill>
<name>tomehub-ingestion-consistency</name>
<description>Diagnose ingestion freshness and consistency in TomeHub by checking ingestion lifecycle, search visibility timing, and vector versus graph readiness.</description>
<location>project</location>
</skill>

<skill>
<name>tomehub-rag-quality-guard</name>
<description>Apply groundedness and retrieval-quality guardrails to TomeHub RAG responses before accepting changes that impact answer quality.</description>
<location>project</location>
</skill>

<skill>
<name>tomehub-search-triage</name>
<description>Diagnose TomeHub search quality issues by isolating retrieval path differences, ranking behavior, and graph/vector contribution in /api/search and /api/smart-search.</description>
<location>project</location>
</skill>

<skill>
<name>tomehub-security-ops</name>
<description>Operational security guardrails for TomeHub engineering tasks including auth checks, sensitive data handling, and safe command boundaries.</description>
<location>project</location>
</skill>

<skill>
<name>ui</name>
<description>React and Tailwind UI implementation guidance for accessible, responsive, production-ready interface work in TomeHub frontend.</description>
<location>project</location>
</skill>

</available_skills>
<!-- SKILLS_TABLE_END -->

</skills_system>

## Repo Operating Notes

### Current Architecture
- Treat `apps/backend` and `apps/frontend` as the primary product code paths.
- Backend is a FastAPI application, not Flask. Main entrypoint: `apps/backend/app.py`.
- Frontend is a Vite + React 19 + TypeScript app. Main entrypoint: `apps/frontend/src/App.tsx`.
- Backend owns AI provider selection, auth policy, ingestion, search, memory, and external API behavior.
- Frontend service names can be misleading:
  - `apps/frontend/src/services/geminiService.ts` is a client-side facade, not the source of truth for active model routing.
  - Model/provider truth lives in `apps/backend/config.py` and backend `services/`.

### Backend Shape
- Core backend areas:
  - `apps/backend/routes/` for modular routers (`ai_routes.py`, `flow_routes.py`, `external_api_routes.py`)
  - `apps/backend/services/` for search, ingestion, AI orchestration, flow, memory, PDF, external KB, and library logic
  - `apps/backend/models/` for request/response models
  - `apps/backend/infrastructure/` for Oracle pool and SQL/migrations
  - `apps/backend/tests/` for the most relevant automated coverage
- Database is Oracle with separate read/write pools. Start from `apps/backend/infrastructure/db_manager.py`.
- Search is hybrid: lexical + semantic + graph + optional external knowledge enrichment. Do not assume a single-path RAG stack.
- PDF ingestion is OCI/Object Storage aware and includes async ingestion/parsing flows. Check `object_storage_service.py`, `pdf_async_ingestion_service.py`, and related config before changing ingestion behavior.
- Auth is Firebase JWT based for user routes. External read-only API has separate controls in backend config.
- Observability is already part of the live architecture:
  - Prometheus metrics
  - Grafana dashboards
  - Loki/Promtail logs
  - Docker Compose in `infra/docker-compose.yml`

### Frontend Shape
- Frontend uses Firebase Auth and talks to backend through `apps/frontend/src/services/apiClient.ts`.
- Library and note flows rely on backend sync, not purely local state.
- Primary frontend areas:
  - `apps/frontend/src/features/`
  - `apps/frontend/src/components/`
  - `apps/frontend/src/services/`
  - `apps/frontend/src/contexts/`
- Media library support is feature-flagged on both frontend and backend. Check both before changing movie/series behavior.

### AI / Model Reality
- Do not assume the project is "Gemini only".
- Standard/backend defaults still use Gemini-family models for many tasks.
- Explorer and advanced orchestration can route through non-Gemini providers via backend config.
- Before making model-related changes, inspect:
  - `apps/backend/config.py`
  - `apps/backend/services/llm_client.py`
  - `apps/backend/services/dual_ai_orchestrator.py`
  - `apps/backend/services/ai_service.py`

### Source Priority
- Use these as primary sources of truth:
  - Active code in `apps/backend` and `apps/frontend`
  - Tests in `apps/backend/tests`
  - Infra config in `infra/`
  - Airflow DAGs in `dags/` when the task is analytics/pipeline related
- Treat these as secondary or historical unless the task explicitly targets them:
  - `documentation/legacy/` (old Flask-era guides)
  - `documentation/reports/` (historical reports, audits, rollout notes)
  - `docs/PHASE_A_PROGRESS.md` (outdated phase checklist)
  - `docs/README.md` (stale template content, not repo architecture truth)
  - `tmp/`, `logs/`, ad-hoc debug scripts and generated artifacts
  - root-level `tests/` before `apps/backend/tests/`

### Working Conventions
- Prefer implementing changes in the active app folders instead of adding more root-level helper scripts.
- If a task touches search quality, ingestion freshness, release safety, UI work, or security, use the matching skill first when available.
- When updating docs or prompts, align terminology with current product naming:
  - backend chat route stays `/api/chat`
  - product wording may refer to LogosChat or Explorer depending on UI context
- Before changing env-sensitive behavior, inspect `.env.example`, `apps/backend/config.py`, and feature flags in frontend env usage.

### Useful Commands
- Frontend:
  - `cd apps/frontend`
  - `npm run dev`
  - `npm run build`
  - `npm run test`
- Backend:
  - `cd apps/backend`
  - `python app.py`
  - `pytest tests -q`
- Infra:
  - `cd infra`
  - `docker compose up -d`

### Cleanup Guidance
- Do not delete historical reports, `tmp/`, or legacy docs automatically during normal feature work.
- If repository cleanup is requested, propose removals first and wait for approval before deleting:
  - stale generated reports
  - temporary probes in `tmp/`
  - legacy Flask documentation
  - duplicate or obsolete root-level test/debug scripts
