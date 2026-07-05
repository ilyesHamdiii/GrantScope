from sqlalchemy import select

from app.db.session import SessionLocal
from app.graph_export import create_bundle_bytes
from app.models.entities import Finding
from app.models.suppression import SuppressionDecision
from app.services.analysis_engine import analyze_import_run
from app.services.baseline_suppression import apply_baseline_suppression
from app.services.bundle_importer import import_bundle_archive


def test_external_low_risk_service_principal_is_suppressed() -> None:
    db = SessionLocal()

    try:
        payload = {
            "manifest.json": {
                "schema_version": "1.0",
                "bundle_name": "baseline-suppression-test",
                "generated_at": "2026-07-04T10:00:00Z",
                "tenant": {
                    "tenant_id": "44444444-4444-4444-4444-444444444444",
                    "display_name": "Baseline Test Tenant",
                },
            },
            "applications.json": [
                {
                    "id": "app-normal-external",
                    "appId": "00000000-0000-0000-0000-000000000099",
                    "displayName": "Normal External Enterprise App",
                }
            ],
            "service_principals.json": [
                {
                    "id": "sp-normal-external",
                    "appId": "00000000-0000-0000-0000-000000000099",
                    "displayName": "Normal External Enterprise App",
                    "servicePrincipalType": "Application",
                    "accountEnabled": True,
                    "appOwnerOrganizationId": "99999999-9999-9999-9999-999999999999",
                    "publisherName": "External Vendor",
                    "tags": [],
                }
            ],
            "owners.json": [],
            "credentials.json": [],
            "oauth2_permission_grants.json": [],
            "app_role_assignments.json": [],
            "directory_audits.json": [],
            "sign_ins.json": [],
        }

        import_run = import_bundle_archive(
            db=db,
            raw_bytes=create_bundle_bytes(payload),
            source_name="baseline-suppression-test.zip",
        )

        analyze_import_run(
            db=db,
            import_run_id=import_run.id,
        )

        result = apply_baseline_suppression(
            db=db,
            import_run_id=import_run.id,
        )

        findings = db.scalars(
            select(Finding).where(
                Finding.import_run_id == import_run.id
            )
        ).all()

        suppressions = db.scalars(
            select(SuppressionDecision).where(
                SuppressionDecision.import_run_id == import_run.id
            )
        ).all()

        assert result["suppression_count"] == 1
        assert result["findings_removed"] == 0
        assert findings == []
        assert len(suppressions) == 1
        assert suppressions[0].suppression_code == "GS-BASELINE-001"
        assert suppressions[0].subject_external_id == "sp-normal-external"

    finally:
        db.close()