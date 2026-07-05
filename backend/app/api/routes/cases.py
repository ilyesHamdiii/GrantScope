from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.case_builder import (
    generate_cases_for_import_run,
    get_case_detail,
    list_cases,
)
from app.services.case_workflow import (
    ALLOWED_DISPOSITIONS,
    ALLOWED_STATUSES,
    get_case_activities,
    get_current_assignee,
    update_case_workflow,
)
from app.services.reporting import (
    build_case_html,
    build_case_markdown,
    build_case_pdf,
)


router = APIRouter(tags=["cases"])


class CaseWorkflowUpdateRequest(BaseModel):
    analyst_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
        description="Name or role of the analyst making the review update.",
    )
    status: str | None = Field(default=None)
    disposition: str | None = Field(default=None)
    note: str | None = Field(default=None, max_length=5000)
    assigned_to: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_request(self) -> "CaseWorkflowUpdateRequest":
        if not any([
            self.status,
            self.disposition,
            self.note,
            self.assigned_to,
        ]):
            raise ValueError(
                "Provide at least one of status, disposition, note, or assigned_to."
            )

        if self.status and self.status not in ALLOWED_STATUSES:
            raise ValueError(
                "Unsupported status. Allowed values: "
                + ", ".join(sorted(ALLOWED_STATUSES))
            )

        if self.disposition and self.disposition not in ALLOWED_DISPOSITIONS:
            raise ValueError(
                "Unsupported disposition. Allowed values: "
                + ", ".join(sorted(ALLOWED_DISPOSITIONS))
            )

        return self


def _decorate_case_with_workflow(
    db: Session,
    case: dict,
) -> dict:
    case["assigned_to"] = get_current_assignee(db, case["id"])
    case["activities"] = get_case_activities(db, case["id"])
    return case


@router.post("/import-runs/{import_run_id}/cases/generate")
def generate_case_packets(
    import_run_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return generate_cases_for_import_run(
            db=db,
            import_run_id=import_run_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error


@router.get("/cases")
def get_cases(
    import_run_id: UUID,
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        _decorate_case_with_workflow(db, case)
        for case in list_cases(
            db=db,
            import_run_id=import_run_id,
        )
    ]


@router.get("/cases/{case_id}")
def get_case(
    case_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    case = get_case_detail(
        db=db,
        case_id=case_id,
    )

    if not case:
        raise HTTPException(
            status_code=404,
            detail="Case was not found.",
        )

    return _decorate_case_with_workflow(db, case)


@router.get("/cases/{case_id}/activities")
def get_case_activity_history(
    case_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    case = get_case_detail(
        db=db,
        case_id=case_id,
    )

    if not case:
        raise HTTPException(
            status_code=404,
            detail="Case was not found.",
        )

    return {
        "case_id": str(case_id),
        "assigned_to": get_current_assignee(db, case_id),
        "activities": get_case_activities(db, case_id),
    }


@router.patch("/cases/{case_id}/workflow")
def update_case_state(
    case_id: UUID,
    payload: CaseWorkflowUpdateRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = update_case_workflow(
            db=db,
            case_id=case_id,
            analyst_name=payload.analyst_name,
            status=payload.status,
            disposition=payload.disposition,
            note=payload.note,
            assigned_to=payload.assigned_to,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    return {
        **result,
        "assigned_to": get_current_assignee(db, case_id),
        "activities": get_case_activities(db, case_id),
    }



@router.get("/cases/{case_id}/report/pdf")
def download_case_pdf_report(
    case_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    report = build_case_pdf(
        db=db,
        case_id=case_id,
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Case was not found.",
        )

    return Response(
        content=report,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="grantscope-case-{case_id}.pdf"'
            )
        },
    )

@router.get("/cases/{case_id}/report/markdown")
def download_case_markdown_report(
    case_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    report = build_case_markdown(
        db=db,
        case_id=case_id,
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Case was not found.",
        )

    return Response(
        content=report,
        media_type="text/markdown",
        headers={
            "Content-Disposition": (
                f'attachment; filename="grantscope-case-{case_id}.md"'
            )
        },
    )


@router.get("/cases/{case_id}/report/html")
def download_case_html_report(
    case_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    report = build_case_html(
        db=db,
        case_id=case_id,
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Case was not found.",
        )

    return Response(
        content=report,
        media_type="text/html",
        headers={
            "Content-Disposition": (
                f'attachment; filename="grantscope-case-{case_id}.html"'
            )
        },
    )