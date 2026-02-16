---
name: tomehub-api-release-gate
description: Enforce pre-release API safety checks for TomeHub backend changes with contract validation, regression checks, and rollout readiness criteria.
---

# TomeHub API Release Gate

Use this skill before merging or deploying backend API changes.

## Triggers
- api release
- pre deploy check
- contract validation
- regression gate
- endpoint change review

## Workflow
1. List changed endpoints and contract-impacting edits.
2. Verify auth, validation, and error-shape consistency.
3. Require targeted tests for changed behavior.
4. Provide release gate verdict: pass, conditional pass, fail.

## References
- Read `references/checklist.md` for release gate criteria.
