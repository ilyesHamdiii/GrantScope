from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AppRoleAssignment,
    Finding,
    ImportRun,
    OAuthPermissionGrant,
    ServicePrincipal,
)
from app.models.finding_evidence import FindingEvidence
from app.models.suppression import SuppressionDecision
from app.services.analysis_engine import PERMISSION_RISKS


BASELINE_ONLY_RULES = {
    "GS-OWNER-001",
    "GS-PUBLISHER-001",
}


def _permission_score(permission_text: str | None) -> int:
    highest_score = 0

    for permission in (permission_text or "").split():
        catalog_entry = PERMISSION_RISKS.get(permission)

        if catalog_entry:
            highest_score = max(
                highest_score,
                int(catalog_entry.get("score", 0)),
            )

    return highest_score


def _assignment_permission_value(
    assignment: AppRoleAssignment,
) -> str | None:
    raw_data = assignment.raw_data or {}

    for key in (
        "appRoleValue",
        "app_role_value",
        "permission",
        "permissionValue",
        "appRoleDisplayName",
    ):
        value = raw_data.get(key)

        if value:
            return str(value)

    return assignment.app_role_id


def serialize_suppression(
    suppression: SuppressionDecision,
) -> dict[str, Any]:
    return {
        "id": str(suppression.id),
        "import_run_id": str(suppression.import_run_id),
        "subject_type": suppression.subject_type,
        "subject_external_id": suppression.subject_external_id,
        "subject_display_name": suppression.subject_display_name,
        "suppression_code": suppression.suppression_code,
        "reason": suppression.reason,
        "context": suppression.context,
        "created_at": (
            suppression.created_at.isoformat()
            if suppression.created_at
            else None
        ),
    }


def list_suppressions(
    db: Session,
    import_run_id: Any,
) -> list[dict[str, Any]]:
    records = db.scalars(
        select(SuppressionDecision)
        .where(SuppressionDecision.import_run_id == import_run_id)
        .order_by(
            SuppressionDecision.subject_display_name.asc()
        )
    ).all()

    return [
        serialize_suppression(record)
        for record in records
    ]


def apply_baseline_suppression(
    db: Session,
    import_run_id: Any,
) -> dict[str, Any]:
    """
    Create auditable suppression records for normal external enterprise
    applications that have no sensitive permissions and no non-baseline
    detection findings.

    This function only removes GS-OWNER-001 and GS-PUBLISHER-001 findings.
    It never removes OAuth-consent, role-assignment, credential, or sequence
    findings.
    """
    import_run = db.get(ImportRun, import_run_id)

    if not import_run:
        raise ValueError("Import run was not found.")

    db.execute(
        delete(SuppressionDecision).where(
            SuppressionDecision.import_run_id == import_run.id
        )
    )
    db.commit()

    service_principals = db.scalars(
        select(ServicePrincipal).where(
            ServicePrincipal.import_run_id == import_run.id
        )
    ).all()

    grants = db.scalars(
        select(OAuthPermissionGrant).where(
            OAuthPermissionGrant.import_run_id == import_run.id
        )
    ).all()

    assignments = db.scalars(
        select(AppRoleAssignment).where(
            AppRoleAssignment.import_run_id == import_run.id
        )
    ).all()

    grants_by_service_principal: dict[
        str,
        list[OAuthPermissionGrant],
    ] = defaultdict(list)

    for grant in grants:
        if grant.client_service_principal_id:
            grants_by_service_principal[
                grant.client_service_principal_id
            ].append(grant)

    assignments_by_service_principal: dict[
        str,
        list[AppRoleAssignment],
    ] = defaultdict(list)

    for assignment in assignments:
        if assignment.principal_id:
            assignments_by_service_principal[
                assignment.principal_id
            ].append(assignment)

    suppression_count = 0
    findings_removed = 0

    for service_principal in service_principals:
        owner_organization_id = (
            service_principal.app_owner_organization_id
        )

        if not owner_organization_id:
            continue

        is_external = (
            str(owner_organization_id).lower()
            != str(import_run.tenant_id).lower()
        )

        if not is_external:
            continue

        related_findings = db.scalars(
            select(Finding).where(
                Finding.import_run_id == import_run.id,
                Finding.subject_type == "service_principal",
                Finding.subject_external_id
                == service_principal.external_id,
            )
        ).all()

        non_baseline_findings = [
            finding
            for finding in related_findings
            if finding.rule_id not in BASELINE_ONLY_RULES
        ]

        if non_baseline_findings:
            continue

        maximum_permission_score = 0

        for grant in grants_by_service_principal.get(
            service_principal.external_id,
            [],
        ):
            maximum_permission_score = max(
                maximum_permission_score,
                _permission_score(grant.scope),
            )

        for assignment in assignments_by_service_principal.get(
            service_principal.external_id,
            [],
        ):
            maximum_permission_score = max(
                maximum_permission_score,
                _permission_score(
                    _assignment_permission_value(assignment)
                ),
            )

        if maximum_permission_score >= 3:
            continue

        baseline_findings = [
            finding
            for finding in related_findings
            if finding.rule_id in BASELINE_ONLY_RULES
        ]

        baseline_finding_ids = [
            finding.id
            for finding in baseline_findings
        ]

        if baseline_finding_ids:
            db.execute(
                delete(FindingEvidence).where(
                    FindingEvidence.finding_id.in_(
                        baseline_finding_ids
                    )
                )
            )

            db.execute(
                delete(Finding).where(
                    Finding.id.in_(baseline_finding_ids)
                )
            )

            findings_removed += len(baseline_finding_ids)

        db.add(
            SuppressionDecision(
                import_run_id=import_run.id,
                subject_type="service_principal",
                subject_external_id=service_principal.external_id,
                subject_display_name=(
                    service_principal.display_name
                    or service_principal.external_id
                ),
                suppression_code="GS-BASELINE-001",
                reason=(
                    "Suppressed from the investigation queue because this "
                    "is an externally owned enterprise application with no "
                    "sensitive resolved permissions and no non-baseline "
                    "detection findings. Missing local owner or publisher "
                    "metadata remains inventory context, not incident evidence."
                ),
                context={
                    "is_external": True,
                    "max_permission_score": maximum_permission_score,
                    "removed_rule_ids": sorted(
                        {
                            finding.rule_id
                            for finding in baseline_findings
                        }
                    ),
                    "non_baseline_findings_present": False,
                },
            )
        )

        suppression_count += 1

    db.commit()

    return {
        "import_run_id": str(import_run.id),
        "suppression_count": suppression_count,
        "findings_removed": findings_removed,
    }