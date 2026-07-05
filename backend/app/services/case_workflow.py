from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.case_activity import CaseActivity
from app.models.entities import InvestigationCase


ALLOWED_STATUSES = {
    "open",
    "under_review",
    "contained",
    "closed",
    "insufficient_evidence",
}

ALLOWED_DISPOSITIONS = {
    "needs_review",
    "likely_benign",
    "suspicious",
    "confirmed_malicious",
    "contained",
    "insufficient_data",
}


def serialize_activity(activity: CaseActivity) -> dict[str, Any]:
    return {
        "id": str(activity.id),
        "case_id": str(activity.case_id),
        "activity_type": activity.activity_type,
        "actor_name": activity.actor_name,
        "note": activity.note,
        "old_status": activity.old_status,
        "new_status": activity.new_status,
        "old_disposition": activity.old_disposition,
        "new_disposition": activity.new_disposition,
        "assigned_to": activity.assigned_to,
        "created_at": (
            activity.created_at.isoformat()
            if activity.created_at
            else None
        ),
    }


def get_case_activities(
    db: Session,
    case_id: Any,
) -> list[dict[str, Any]]:
    activities = db.scalars(
        select(CaseActivity)
        .where(CaseActivity.case_id == case_id)
        .order_by(CaseActivity.created_at.asc())
    ).all()

    return [serialize_activity(activity) for activity in activities]


def get_current_assignee(
    db: Session,
    case_id: Any,
) -> str | None:
    activities = db.scalars(
        select(CaseActivity)
        .where(
            CaseActivity.case_id == case_id,
            CaseActivity.assigned_to.is_not(None),
        )
        .order_by(CaseActivity.created_at.desc())
    ).all()

    if not activities:
        return None

    return activities[0].assigned_to


def update_case_workflow(
    db: Session,
    *,
    case_id: Any,
    analyst_name: str,
    status: str | None = None,
    disposition: str | None = None,
    note: str | None = None,
    assigned_to: str | None = None,
) -> dict[str, Any]:
    investigation_case = db.get(InvestigationCase, case_id)

    if not investigation_case:
        raise ValueError("Case was not found.")

    if status is not None and status not in ALLOWED_STATUSES:
        raise ValueError(f"Unsupported case status: {status}")

    if disposition is not None and disposition not in ALLOWED_DISPOSITIONS:
        raise ValueError(f"Unsupported case disposition: {disposition}")

    if not any([status, disposition, note, assigned_to]):
        raise ValueError(
            "Provide at least one of status, disposition, note, or assigned_to."
        )

    old_status = investigation_case.status
    old_disposition = investigation_case.disposition

    if status is not None:
        investigation_case.status = status

    if disposition is not None:
        investigation_case.disposition = disposition

    investigation_case.updated_at = datetime.now(timezone.utc)

    state_changed = (
        old_status != investigation_case.status
        or old_disposition != investigation_case.disposition
    )

    if assigned_to and state_changed:
        activity_type = "state_update_and_assignment"
    elif assigned_to:
        activity_type = "assignment"
    elif state_changed:
        activity_type = "state_update"
    else:
        activity_type = "analyst_note"

    activity = CaseActivity(
        case_id=investigation_case.id,
        activity_type=activity_type,
        actor_name=analyst_name,
        note=note,
        old_status=old_status,
        new_status=investigation_case.status,
        old_disposition=old_disposition,
        new_disposition=investigation_case.disposition,
        assigned_to=assigned_to,
    )

    db.add(activity)
    db.commit()
    db.refresh(investigation_case)
    db.refresh(activity)

    return {
        "case_id": str(investigation_case.id),
        "status": investigation_case.status,
        "disposition": investigation_case.disposition,
        "activity": serialize_activity(activity),
    }