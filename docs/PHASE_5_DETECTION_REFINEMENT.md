# GrantScope Phase 5: Detection Refinement and Analyst Workflow

## Detection changes

GrantScope now evaluates ownership using this order:

1. Active service-principal owner
2. Active linked application owner
3. No active owner found in imported evidence

This reduces false positives when exports contain application ownership but omit service-principal ownership.

## Permission context

Sensitive permission findings now attach evidence describing:

- Permission type: delegated or application
- Consent scope: tenant-wide or application-level
- Resource API
- Blast radius
- Potential impact

## Critical sequence logic

`GS-SEQUENCE-001` now requires:

1. A high-impact app-role assignment within 24 hours before a credential event
2. A credential event or inferred credential activation time
3. First service-principal use within 60 minutes after that credential event

## Case workflow

Cases support persisted analyst review activity:

- Status
- Disposition
- Assignment
- Analyst note
- Full review history

## Important limitation

V1 does not yet provide authentication, role-based access control, or immutable audit logging. Workflow state is suitable for a portfolio prototype, not a multi-tenant production deployment.