from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.entities import Finding
from app.services.analysis_engine import analyze_import_run
from app.services.bundle_importer import import_bundle_archive


def test_demo_bundle_detects_risky_sequences_without_high_benign_findings() -> None:
    db = SessionLocal()

    try:
        bundle_path = Path("/app/sample-data/demo-tenant.zip")

        import_run = import_bundle_archive(
            db=db,
            raw_bytes=bundle_path.read_bytes(),
            source_name="demo-tenant-test.zip",
        )

        result = analyze_import_run(db, import_run.id)

        findings = db.scalars(
            select(Finding).where(Finding.import_run_id == import_run.id)
        ).all()

        benign_findings = [
            finding
            for finding in findings
            if finding.subject_external_id == "sp-northbridge-meetings"
        ]

        assert not any(
            finding.severity in {"high", "critical"}
            for finding in benign_findings
        )

        assert result["severity_counts"]["critical"] >= 1

        assert any(
            finding.rule_id == "GS-SEQUENCE-001"
            and finding.subject_external_id == "sp-provisioning-bridge"
            for finding in findings
        )

        assert any(
            finding.rule_id == "GS-OAUTH-001"
            and finding.subject_external_id == "sp-cloudsync-assistant"
            for finding in findings
        )

        assert any(
            finding.rule_id == "GS-ROLE-001"
            and finding.subject_external_id == "sp-directory-admin-integration"
            for finding in findings
        )

    finally:
        db.close()