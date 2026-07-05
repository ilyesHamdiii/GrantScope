from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Finding
from app.services.analysis_engine import (
    analyze_import_run,
    list_findings,
    serialize_finding,
)
from app.services.baseline_suppression import (
    apply_baseline_suppression,
    list_suppressions,
)


router = APIRouter(tags=["analysis"])


@router.post("/import-runs/{import_run_id}/analyze")
def analyze_evidence_bundle(
    import_run_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    try:
        analysis_result = analyze_import_run(
            db=db,
            import_run_id=import_run_id,
        )

        suppression_result = apply_baseline_suppression(
            db=db,
            import_run_id=import_run_id,
        )

        analysis_result["suppression_count"] = (
            suppression_result["suppression_count"]
        )

        analysis_result["findings_removed_by_baseline"] = (
            suppression_result["findings_removed"]
        )

        analysis_result["finding_count"] = len(
            list_findings(
                db=db,
                import_run_id=import_run_id,
            )
        )

        return analysis_result

    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error


@router.get("/findings")
def get_findings(
    import_run_id: UUID,
    severity: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict]:
    return list_findings(
        db=db,
        import_run_id=import_run_id,
        severity=severity,
    )


@router.get("/findings/{finding_id}")
def get_finding_detail(
    finding_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    finding = db.get(Finding, finding_id)

    if not finding:
        raise HTTPException(
            status_code=404,
            detail="Finding was not found.",
        )

    return serialize_finding(
        db=db,
        finding=finding,
    )


@router.get("/suppressions")
def get_suppressions(
    import_run_id: UUID,
    db: Session = Depends(get_db),
) -> list[dict]:
    return list_suppressions(
        db=db,
        import_run_id=import_run_id,
    )