---
name: guard
description: Security and authorization guardrails for authentication, permissions, tokens, and sensitive operations.
---

# Guard Skill

Use this skill for auth, permissions, role checks, token handling, and secure-by-default decisions.

## Triggers
- auth
- permission
- role
- token
- security
- access control

## Rules
1. Default deny unless explicitly allowed.
2. Validate identity and authorization separately.
3. Never rely on implicit trust from client input.
4. Fail closed with explicit audit-friendly errors.
