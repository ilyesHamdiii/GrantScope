from pathlib import Path

from app.db.session import SessionLocal
from app.services.analysis_engine import analyze_import_run
from app.services.bundle_importer import import_bundle_archive
from app.services.case_builder import generate_cases_for_import_run
from app.services.reporting import build_case_pdf


def test_critical_case_generates_a_valid_pdf_report() -> None:
    db = SessionLocal()

    try:
        bundle_path = Path("/app/sample-data/demo-tenant.zip")

        import_run = import_bundle_archive(
            db=db,
            raw_bytes=bundle_path.read_bytes(),
            source_name="demo-tenant-pdf-report-test.zip",
        )

        analyze_import_run(db, import_run.id)
        generated = generate_cases_for_import_run(db, import_run.id)

        critical_case = next(
            case
            for case in generated["cases"]
            if case["severity"] == "critical"
        )

        pdf_bytes = build_case_pdf(
            db=db,
            case_id=critical_case["id"],
        )

        assert pdf_bytes is not None
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 5000

    finally:
        db.close()