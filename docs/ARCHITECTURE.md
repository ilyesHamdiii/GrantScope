# GrantScope Architecture

## Product boundary

GrantScope is an Entra OAuth and service-principal investigation workbench.

It receives structured evidence, applies explainable correlation logic, and produces analyst case packets.

It is not a SIEM replacement, generic cloud posture dashboard, automatic containment system, or malware-reputation engine.

## Logical flow

~~~text
Evidence bundle
    |
    v
FastAPI import API
    |
    v
Normalization layer
    |
    v
PostgreSQL evidence model
    |
    +--> Inventory endpoints
    |
    +--> Detection and correlation engine
              |
              v
         Explainable findings
              |
              v
         Case packet generator
              |
              +--> Workflow history
              +--> Timeline
              +--> Evidence index
              +--> HTML / Markdown / PDF reports
              |
              v
         React investigation workbench
~~~

## Main evidence entities

~~~text
ImportRun
ImportedArtifact
Application
ServicePrincipal
Ownership
Credential
OAuthPermissionGrant
AppRoleAssignment
DirectoryAuditEvent
SignInEvent
Finding
FindingEvidence
InvestigationCase
CaseEvidence
CaseActivity
~~~

## Detection rules

| Rule | Purpose |
|---|---|
| GS-OAUTH-001 | Tenant-wide delegated consent with sensitive scopes |
| GS-ROLE-001 | High-impact application permission assignment |
| GS-OWNER-001 | No active service-principal or linked-application owner |
| GS-PUBLISHER-001 | External service principal with no verified publisher metadata |
| GS-CRED-001 | Excessive credential lifetime |
| GS-CRED-002 | Credential present on a privileged service principal |
| GS-SEQUENCE-001 | Privileged assignment, credential event, then rapid first use |

## Severity and confidence

Severity answers:

> If this activity were abused, how damaging could it be?

Confidence answers:

> How strong is the imported evidence that this requires investigation?

GrantScope keeps them separate to avoid treating high-impact permissions as proof of maliciousness.