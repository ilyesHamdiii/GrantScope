from pathlib import Path

from app.db.session import SessionLocal
from app.services.analysis_engine import analyze_import_run
from app.services.bundle_importer import import_bundle_archive
from app.services.case_builder import generate_cases_for_import_run
from app.services.case_workflow import (
    get_case_activities,
    get_current_assignee,
    update_case_workflow,
)


def test_case_workflow_persists_state_assignment_and_notes() -> None:
    db = SessionLocal()

    try:
        bundle_path = Path("/app/sample-data/demo-tenant.zip")

        import_run = import_bundle_archive(
            db=db,
            raw_bytes=bundle_path.read_bytes(),
            source_name="demo-tenant-workflow-test.zip",
        )

        analyze_import_run(db, import_run.id)
        generated = generate_cases_for_import_run(db, import_run.id)

        provisioning_case = next(
            case
            for case in generated["cases"]
            if "Provisioning Bridge" in case["title"]
        )

        update = update_case_workflow(
            db=db,
            case_id=provisioning_case["id"],
            analyst_name="Demo Analyst",
            status="under_review",
            disposition="suspicious",
            assigned_to="Cloud Identity Analyst",
            note="Validated the role assignment, credential event, and first-use sequence.",
        )

        assert update["status"] == "under_review"
        assert update["disposition"] == "suspicious"
        assert get_current_assignee(db, provisioning_case["id"]) == "Cloud Identity Analyst"

        activities = get_case_activities(db, provisioning_case["id"])

        assert len(activities) == 1
        assert activities[0]["activity_type"] == "state_update_and_assignment"
        assert "Validated the role assignment" in activities[0]["note"]

    finally:
        db.close()