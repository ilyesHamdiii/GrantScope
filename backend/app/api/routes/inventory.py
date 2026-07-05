from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Application, ServicePrincipal


router = APIRouter(tags=["inventory"])


@router.get("/inventory/service-principals")
def list_service_principals(
    import_run_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict]:
    statement = (
        select(ServicePrincipal)
        .where(ServicePrincipal.import_run_id == import_run_id)
        .order_by(ServicePrincipal.display_name.asc())
        .limit(limit)
    )

    service_principals = db.scalars(statement).all()

    return [
        {
            "id": str(service_principal.id),
            "external_id": service_principal.external_id,
            "app_id": service_principal.app_id,
            "display_name": service_principal.display_name,
            "service_principal_type": service_principal.service_principal_type,
            "account_enabled": service_principal.account_enabled,
            "publisher_name": service_principal.publisher_name,
            "verified_publisher_name": service_principal.verified_publisher_name,
            "tags": service_principal.tags,
        }
        for service_principal in service_principals
    ]


@router.get("/inventory/applications")
def list_applications(
    import_run_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict]:
    statement = (
        select(Application)
        .where(Application.import_run_id == import_run_id)
        .order_by(Application.display_name.asc())
        .limit(limit)
    )

    applications = db.scalars(statement).all()

    return [
        {
            "id": str(application.id),
            "external_id": application.external_id,
            "app_id": application.app_id,
            "display_name": application.display_name,
            "created_datetime": (
                application.created_datetime.isoformat()
                if application.created_datetime
                else None
            ),
            "sign_in_audience": application.sign_in_audience,
            "publisher_domain": application.publisher_domain,
            "verified_publisher_name": application.verified_publisher_name,
        }
        for application in applications
    ]