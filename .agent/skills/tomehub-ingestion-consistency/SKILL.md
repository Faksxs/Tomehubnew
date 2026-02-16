---
name: tomehub-ingestion-consistency
description: Diagnose ingestion freshness and consistency in TomeHub by checking ingestion lifecycle, search visibility timing, and vector versus graph readiness.
---

# TomeHub Ingestion Consistency

Use this skill when newly ingested content is delayed, partially visible, or inconsistent across search paths.

## Triggers
- ingestion delay
- eventual consistency
- missing newly added content
- vector ready
- graph ready

## Workflow
1. Confirm ingestion path and content type.
2. Check ingestion status and timing window.
3. Distinguish vector visibility from graph enrichment readiness.
4. Produce an operator action plan with expected recovery time.

## References
- Read `references/checklist.md` for consistency diagnostics.
