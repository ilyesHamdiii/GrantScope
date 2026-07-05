# GrantScope Phase 10: Baseline-Aware Detection

GrantScope now suppresses normal external enterprise service principals from the investigation queue when they have no material risk evidence.

A service principal can be baseline-suppressed only when all conditions are true:

- It is externally owned.
- It has no sensitive resolved delegated or application permissions.
- It has no credential metadata.
- It has no recent identity-management change in the imported audit evidence.
- It has no elevated sign-in risk in imported telemetry.
- Its only findings are missing owner and/or unverified publisher context.

Suppressed records remain auditable through:

GET /api/v1/suppressions?import_run_id={import_run_id}

Suppression code:

GS-BASELINE-001

This prevents normal enterprise service principals from generating cases solely because local owner or publisher metadata is incomplete.