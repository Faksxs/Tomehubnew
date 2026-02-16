# Security Ops Checklist

## Auth and authorization
1. Sensitive actions require explicit auth checks.
2. Permission checks are server-side and role-aware.
3. Failure modes are deny-by-default.

## Sensitive data handling
1. No credentials or tokens in code, logs, or responses.
2. Redact high-risk fields in diagnostics.
3. Validate secrets are sourced from environment or vault.

## Operational safety
1. Avoid destructive commands without explicit confirmation path.
2. Ensure migration and cleanup commands are scoped.
3. Keep audit trail for high-risk operations.

## Output format
1. Severity-ranked findings.
2. Immediate mitigations.
3. Follow-up hardening actions.
