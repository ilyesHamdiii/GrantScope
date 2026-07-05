# GrantScope Phase 7: PDF Case Reporting

## Endpoint

GET /api/v1/cases/{case_id}/report/pdf

## Report source

The PDF is rendered from the same HTML evidence report used by GrantScope. This avoids separate report logic drifting over time.

## Report contents

- Case severity, confidence, workflow status, and disposition
- Executive assessment
- Detection findings and rationale
- Evidence timeline
- Evidence index with source and correlation IDs
- Benign-validation checklist
- Recommended human-review actions
- Missing-data notes

## Security boundary

GrantScope reports identity investigation metadata and evidence only. It does not store or print client secrets, access tokens, refresh tokens, or raw credential material.