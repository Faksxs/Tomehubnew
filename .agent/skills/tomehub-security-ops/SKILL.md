---
name: tomehub-security-ops
description: Operational security guardrails for TomeHub engineering tasks including auth checks, sensitive data handling, and safe command boundaries.
---

# TomeHub Security Ops

Use this skill for security-sensitive code changes, operational reviews, and incident-preventive checks.

## Triggers
- security review
- auth hardening
- token handling
- sensitive data
- destructive command risk

## Workflow
1. Identify trust boundaries and privileged actions.
2. Validate auth and permission enforcement points.
3. Check for secret leakage or unsafe operational commands.
4. Return a prioritized risk list and mitigation steps.

## References
- Read `references/checklist.md` for the security ops checklist.
