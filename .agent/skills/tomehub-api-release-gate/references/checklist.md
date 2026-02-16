# API Release Gate Checklist

## Contract safety
1. Request and response models are explicit and version-safe.
2. Error payload shape is stable and documented.
3. Auth requirements are unchanged or intentionally documented.

## Regression coverage
1. Changed endpoints have direct tests.
2. Critical existing behavior still has coverage.
3. Negative path and auth failure tests are included.

## Operational readiness
1. Logging and monitoring impact is known.
2. Backward compatibility risk is stated.
3. Rollback strategy is documented.

## Verdict format
1. Pass, conditional pass, or fail.
2. Blocking issues.
3. Required follow-up actions.
