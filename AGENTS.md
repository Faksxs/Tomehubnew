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
