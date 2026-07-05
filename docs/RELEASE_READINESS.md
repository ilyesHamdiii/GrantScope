# GrantScope Release Readiness

## Verification Date

2026-07-05 17:55:14 +01:00

## Release Gate Results

- API health endpoint: passed
- Backend test suite: passed
- Frontend production build: passed
- .env excluded from Git tracking: passed
- Local Graph exports excluded from Git tracking: passed
- Local evidence screenshots excluded from Git tracking: passed

## Latest Live Tenant Validation

- Tenant: GrantScope Lab Tenant
- Latest import run: 97df6feb-6dc5-4fac-b963-22662fc5e201
- Imported bundle: grantscope-graph-export-20260704T085844Z.zip
- Current investigation case count: 0

## Demonstrated End-to-End Flow

1. Read-only Microsoft Graph collection using application credentials.
2. Local Graph evidence ZIP generation.
3. ZIP import and normalization in GrantScope.
4. OAuth, service-principal, credential, ownership, audit, and sign-in correlation.
5. Explainable analyst case generation with evidence timelines.
6. False-positive reduction for normal external enterprise applications.
7. Detection of a tenant-owned application ownership gap.
8. Owner assignment in Entra.
9. Fresh evidence collection validating the remediation outcome.

## Security Notes

GrantScope is an export-first local cloud-identity investigation prototype.

Never commit:

- .env
- Microsoft Graph client secrets
- export ZIP files
- screenshots containing private tenant information
- raw evidence files from real environments