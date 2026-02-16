---
name: tomehub-rag-quality-guard
description: Apply groundedness and retrieval-quality guardrails to TomeHub RAG responses before accepting changes that impact answer quality.
---

# TomeHub RAG Quality Guard

Use this skill when validating answer quality, citation grounding, retrieval adequacy, and hallucination risk.

## Triggers
- groundedness
- hallucination risk
- rag quality
- citation quality
- answer reliability

## Workflow
1. Check whether answer claims are supported by retrieved evidence.
2. Flag unsupported synthesis and evidence gaps.
3. Separate retrieval failure from generation failure.
4. Recommend an actionable fix with measurable validation.

## References
- Read `references/checklist.md` for guard criteria.
