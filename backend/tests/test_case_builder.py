from pathlib import Path

from app.db.session import SessionLocal
from app.services.analysis_engine import analyze_import_run
from app.services.bundle_importer import import_bundle_archive
from app.services.case_builder import (
    generate_cases_for_import_run,
    get_case_detail,
)


def test_demo_findings_are_grouped_into_three_case_packets() -> None:
    db = SessionLocal()

    try:
        bundle_path = Path("/app/sample-data/demo-tenant.zip")

        import_run = import_bundle_archive(
            db=db,
            raw_bytes=bundle_path.read_bytes(),
            source_name="demo-tenant-case-builder-test.zip",
        )

        analyze_import_run(db, import_run.id)

        result = generate_cases_for_import_run(db, import_run.id)

        assert result["case_count"] == 3

        provisioning_case = next(
            case
            for case in result["cases"]
            if "Provisioning Bridge" in case["title"]
        )

        assert provisioning_case["severity"] == "critical"
        assert provisioning_case["finding_count"] >= 5
        assert provisioning_case["evidence_count"] >= 4

        detail = get_case_detail(db, provisioning_case["id"])

        assert detail is not None
        assert len(detail["timeline"]) >= 2
        assert any(
            finding["rule_id"] == "GS-SEQUENCE-001"
            for finding in detail["findings"]
        )
        assert any(
            event["source_table"] == "sign_in_events"
            for event in detail["timeline"]
        )

    finally:
        db.close()