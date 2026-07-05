from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.entities import Finding
from app.services.analysis_engine import analyze_import_run
from app.services.bundle_importer import import_bundle_archive


def test_owner_fallback_and_sequence_refinement() -> None:
    db = SessionLocal()

    try:
        bundle_path = Path("/app/sample-data/demo-tenant.zip")

        import_run = import_bundle_archive(
            db=db,
            raw_bytes=bundle_path.read_bytes(),
            source_name="demo-tenant-refinement-test.zip",
        )

        result = analyze_import_run(db, import_run.id)

        findings = db.scalars(
            select(Finding).where(Finding.import_run_id == import_run.id)
        ).all()

        benign_owner_findings = [
            finding
            for finding in findings
            if finding.subject_external_id == "sp-northbridge-meetings"
            and finding.rule_id == "GS-OWNER-001"
        ]

        assert not benign_owner_findings

        provisioning_sequence = next(
            finding
            for finding in findings
            if finding.subject_external_id == "sp-provisioning-bridge"
            and finding.rule_id == "GS-SEQUENCE-001"
        )

        assert provisioning_sequence.severity == "critical"
        assert provisioning_sequence.confidence == "high"

        cloudsync_oauth = next(
            finding
            for finding in findings
            if finding.subject_external_id == "sp-cloudsync-assistant"
            and finding.rule_id == "GS-OAUTH-001"
        )

        assert cloudsync_oauth.severity == "high"
        assert result["severity_counts"]["critical"] >= 1

    finally:
        db.close()