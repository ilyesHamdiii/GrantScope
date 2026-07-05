# GrantScope

GrantScope is an evidence-driven investigation workbench for Entra OAuth applications and service principals.

It helps an analyst move from raw tenant evidence to an explainable case packet:

- Which application or service principal changed?
- What permissions or credentials increased blast radius?
- Is consent tenant-wide or user-scoped?
- Is there an accountable active owner?
- Did privileged assignment, credential activity, and first use form a suspicious sequence?
- What evidence should be reviewed before containment?

GrantScope is an investigation product, not a generic posture dashboard.

## Core capabilities

- Import-first workflow using Graph-style evidence ZIP bundles
- Application and service-principal inventory
- Delegated OAuth grant analysis
- Application permission and app-role assignment analysis
- Credential lifetime checks
- Ownership evaluation with linked-application fallback
- Publisher and provenance context
- Correlation of privileged assignment, credential activity, and rapid first use
- Explainable findings with severity, confidence, evidence, and missing-data notes
- Analyst case packets with timelines and evidence indexes
- Analyst workflow state, assignment, notes, and review history
- HTML, Markdown, and PDF case reports
- React investigation workbench

## Demonstration scenario

The included synthetic tenant bundle contains one benign application and three risky investigation scenarios.

| Scenario | Expected outcome |
|---|---|
| NorthBridge Meetings | Benign collaboration app; should not receive high or critical findings |
| CloudSync Assistant | Tenant-wide delegated consent with sensitive permissions and weak provenance context |
| Provisioning Bridge | Critical sequence: privileged permission, credential addition, rapid service-principal use |
| Directory Administration Integration | High-impact directory-management permission with weak ownership and publisher context |

## Architecture

~~~text
Graph-style evidence ZIP
        |
        v
FastAPI import endpoint
        |
        v
Normalization layer
        |
        v
PostgreSQL evidence model
        |
        +--> Detection and correlation engine
        |          |
        |          v
        |     Explainable findings
        |          |
        |          v
        |     Investigation case packets
        |
        +--> React workbench
                   |
                   +--> Analyst workflow
                   +--> HTML report
                   +--> Markdown report
                   +--> PDF report
~~~

## Local stack

| Component | Technology |
|---|---|
| API | FastAPI |
| Database | PostgreSQL |
| Correlation engine | Python |
| Frontend | React and Vite |
| PDF generation | WeasyPrint |
| Runtime | Docker Compose |

## Start locally

~~~powershell
docker compose up --build -d
~~~

Open:

~~~text
Workbench: http://localhost:5173
API docs:  http://localhost:8000/docs
Health:    http://localhost:8000/health
~~~

## Run the demonstration

~~~powershell
.\scripts\run-demo.ps1
~~~

## Verify the project

~~~powershell
.\scripts\verify-project.ps1
~~~

## Security boundary

GrantScope does not store or print:

- Client secrets
- Access tokens
- Refresh tokens
- Private certificate material
- Raw password credential values

Only credential metadata, evidence references, audit identifiers, and correlation context are retained.

## Current limitations

- The permission-risk catalogue is intentionally narrow and focused on high-impact permissions.
- Live Microsoft Graph collection is planned but not yet implemented.
- The local prototype has no authentication, RBAC, tenant isolation, or immutable audit trail.
- Sample data is synthetic and must not be confused with a real tenant export.

## Documentation

- docs\ARCHITECTURE.md
- docs\DEMO_WALKTHROUGH.md
- docs\SECURITY_AND_LIMITATIONS.md
- docs\GRAPH_CONNECTOR_PLAN.md
- docs\PHASE_7_PDF_REPORTING.md