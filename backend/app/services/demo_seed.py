from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import ImportRun
from app.services.analysis_engine import analyze_import_run
from app.services.bundle_importer import import_bundle_archive
from app.services.case_builder import generate_cases_for_import_run


def seed_public_demo(db: Session) -> None:
    """
    Seed one synthetic NorthBridge investigation run exactly once.

    This function runs only when PUBLIC_DEMO_MODE=true. It never calls
    Microsoft Graph, never loads tenant credentials, and never accepts
    live tenant evidence.
    """
    existing_run = db.scalar(
        select(ImportRun)
        .where(
            ImportRun.source_name == settings.DEMO_SEED_SOURCE_NAME
        )
        .limit(1)
    )

    if existing_run:
        return

    bundle_path = Path(settings.DEMO_SEED_BUNDLE_PATH)

    if not bundle_path.is_file():
        raise RuntimeError(
            "Public demo seed bundle was not found: "
            f"{bundle_path}"
        )

    import_run = import_bundle_archive(
        db=db,
        raw_bytes=bundle_path.read_bytes(),
        source_name=settings.DEMO_SEED_SOURCE_NAME,
    )

    analyze_import_run(
        db=db,
        import_run_id=import_run.id,
    )

    generate_cases_for_import_run(
        db=db,
        import_run_id=import_run.id,
    )