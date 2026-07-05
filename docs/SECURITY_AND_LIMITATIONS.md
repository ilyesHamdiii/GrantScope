# GrantScope Security Design and Limitations

## Evidence-based analysis

Every finding includes:

- Rule identifier
- Severity
- Confidence
- Rationale
- Evidence references
- Missing-data notes
- Benign-verification checklist

## No secret retention

GrantScope intentionally excludes:

- Client secret values
- Password credential values
- Access tokens
- Refresh tokens
- Certificate private keys

Credential metadata such as key ID, display name, start date, and expiry date may be retained for investigation.

## Explainability boundary

GrantScope does not classify an application as malicious solely because it is:

- Externally owned
- Unverified
- Highly privileged
- Newly created
- Missing an owner

Those factors increase review priority but require human validation.

## Current limitations

- Permission coverage is intentionally narrow in the MVP.
- Import completeness affects investigation confidence.
- Sign-in analysis depends on imported sign-in evidence and retention coverage.
- No multi-user authentication, RBAC, immutable audit logging, or tenant isolation exists yet.
- GrantScope recommends containment actions but does not change tenant configuration automatically.