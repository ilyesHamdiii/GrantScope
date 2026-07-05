from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import ImportRun
from app.services.analysis_engine import analyze_import_run
from app.services.bundle_importer import import_bundle_archive
from app.services.case_builder import generate_cases_for_import_run


REQUIRED_BUNDLE_FILES = {
    "manifest.json",
    "applications.json",
    "service_principals.json",
    "owners.json",
    "credentials.json",
    "oauth2_permission_grants.json",
    "app_role_assignments.json",
    "directory_audits.json",
    "sign_ins.json",
}


def build_bundle_from_directory(bundle_directory: Path) -> bytes:
    """
    Build a valid in-memory GrantScope ZIP from committed synthetic JSON files.

    The public deployment does not rely on local ZIP files because ZIP exports
    are intentionally excluded from Git.
    """
    if not bundle_directory.is_dir():
        raise RuntimeError(
            "Public demo seed directory was not found: "
            f"{bundle_directory}"
        )

    available_files = {
        item.name
        for item in bundle_directory.iterdir()
        if item.is_file()
    }

    missing_files = sorted(
        REQUIRED_BUNDLE_FILES - available_files
    )

    if missing_files:
        raise RuntimeError(
            "Public demo seed directory is incomplete. Missing: "
            + ", ".join(missing_files)
        )

    buffer = BytesIO()

    with ZipFile(
        buffer,
        mode="w",
        compression=ZIP_DEFLATED,
    ) as archive:
        for filename in sorted(REQUIRED_BUNDLE_FILES):
            source_file = bundle_directory / filename
            archive.writestr(
                filename,
                source_file.read_bytes(),
            )

    return buffer.getvalue()


def load_seed_bundle(bundle_path: Path) -> bytes:
    """
    Prefer the ZIP locally. On Render, rebuild it from the tracked JSON folder.
    """
    if bundle_path.is_file():
        return bundle_path.read_bytes()

    return build_bundle_from_directory(
        bundle_path.with_suffix("")
    )


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

    import_run = import_bundle_archive(
        db=db,
        raw_bytes=load_seed_bundle(bundle_path),
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