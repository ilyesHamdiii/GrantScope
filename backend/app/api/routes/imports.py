from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.entities import ImportRun
from app.services.bundle_importer import (
    BundleValidationError,
    build_import_summary,
    import_bundle_archive,
    serialize_import_run,
)


router = APIRouter(tags=["imports"])


@router.post("/imports/bundle", status_code=status.HTTP_201_CREATED)
async def import_evidence_bundle(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    file_name = file.filename or "uploaded-evidence-bundle.zip"

    if not file_name.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GrantScope accepts .zip evidence bundles only.",
        )

    raw_bytes = await file.read()

    if len(raw_bytes) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Evidence bundle exceeds the current 25 MB upload limit.",
        )

    try:
        import_run = import_bundle_archive(
            db=db,
            raw_bytes=raw_bytes,
            source_name=file_name,
        )
    except BundleValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    return build_import_summary(db, import_run)


@router.get("/import-runs")
def list_import_runs(
    db: Session = Depends(get_db),
) -> list[dict]:
    statement = select(ImportRun).order_by(ImportRun.created_at.desc())
    import_runs = db.scalars(statement).all()

    return [serialize_import_run(import_run) for import_run in import_runs]


@router.get("/import-runs/{import_run_id}/summary")
def get_import_run_summary(
    import_run_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    import_run = db.get(ImportRun, import_run_id)

    if not import_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import run was not found.",
        )

    return build_import_summary(db, import_run)