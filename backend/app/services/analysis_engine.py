from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AppRoleAssignment,
    Application,
    Credential,
    DirectoryAuditEvent,
    Finding,
    ImportRun,
    OAuthPermissionGrant,
    Ownership,
    ServicePrincipal,
    SignInEvent,
)
from app.models.finding_evidence import FindingEvidence
from app.models.suppression import SuppressionDecision


PERMISSION_RISKS: dict[str, dict[str, Any]] = {
    "RoleManagement.ReadWrite.Directory": {
        "score": 5,
        "blast_radius": "Tenant-wide privileged identity administration",
        "impact": (
            "Can modify directory role-management and privileged-access settings."
        ),
    },
    "Application.ReadWrite.All": {
        "score": 5,
        "blast_radius": "Tenant-wide application persistence and configuration",
        "impact": (
            "Can create, update, or delete application registrations and credentials."
        ),
    },
    "AppRoleAssignment.ReadWrite.All": {
        "score": 5,
        "blast_radius": "Tenant-wide application privilege assignment",
        "impact": (
            "Can create or modify application role assignments."
        ),
    },
    "Directory.ReadWrite.All": {
        "score": 4,
        "blast_radius": "Broad directory modification",
        "impact": "Can modify broad directory objects and settings.",
    },
    "Sites.FullControl.All": {
        "score": 5,
        "blast_radius": "Full SharePoint tenant-content control",
        "impact": (
            "Can fully control SharePoint site content and configuration."
        ),
    },
    "Sites.ReadWrite.All": {
        "score": 4,
        "blast_radius": "Broad SharePoint content modification",
        "impact": "Can read and modify SharePoint site content.",
    },
    "Files.ReadWrite.All": {
        "score": 4,
        "blast_radius": "Broad file modification",
        "impact": (
            "Can read and modify files accessible through Microsoft Graph."
        ),
    },
    "Mail.ReadWrite": {
        "score": 4,
        "blast_radius": "Mail-content access and modification",
        "impact": "Can read and modify mail data.",
    },
    "Mail.Send": {
        "score": 3,
        "blast_radius": "Outbound mailbox impersonation risk",
        "impact": (
            "Can send email as the signed-in user or application context."
        ),
    },
    "User.ReadWrite.All": {
        "score": 4,
        "blast_radius": "Broad user directory modification",
        "impact": "Can read and modify user directory data.",
    },
    "Group.ReadWrite.All": {
        "score": 4,
        "blast_radius": "Broad group membership and settings modification",
        "impact": "Can read and modify group memberships and settings.",
    },
    "offline_access": {
        "score": 1,
        "blast_radius": "Long-lived delegated access",
        "impact": (
            "Can maintain delegated access through refresh-token capability."
        ),
    },
}

FIRST_PARTY_MARKERS = (
    "microsoft",
    "azure",
    "office",
    "entra",
    "aad",
    "windows",
)


@dataclass
class EvidenceItem:
    evidence_type: str
    source_table: str
    source_external_id: str | None
    label: str
    detail: str | None = None
    observed_at: datetime | None = None
    correlation_id: str | None = None
    raw_reference: dict[str, Any] = field(default_factory=dict)


def _normalize_resource_type(value: str | None) -> str:
    return (value or "").replace("_", "").replace("-", "").lower()


def _permission_assessment(
    permission_text: str | None,
) -> tuple[list[str], int]:
    matched_permissions: list[str] = []
    max_score = 0

    for token in (permission_text or "").split():
        item = PERMISSION_RISKS.get(token)

        if not item:
            continue

        matched_permissions.append(token)
        max_score = max(max_score, int(item["score"]))

    return matched_permissions, max_score


def _app_role_value(
    assignment: AppRoleAssignment,
) -> str | None:
    raw = assignment.raw_data or {}

    for key in (
        "appRoleValue",
        "app_role_value",
        "permission",
        "permissionValue",
        "appRoleDisplayName",
    ):
        value = raw.get(key)

        if value:
            return str(value)

    return assignment.app_role_id


def _audit_targets(
    audit: DirectoryAuditEvent,
) -> set[str]:
    targets: set[str] = set()

    for target in audit.target_resources or []:
        if not isinstance(target, dict):
            continue

        for key in ("id", "appId", "servicePrincipalId"):
            value = target.get(key)

            if value:
                targets.add(str(value))

    return targets


def _likely_first_party(
    service_principal: ServicePrincipal,
) -> bool:
    values = [
        service_principal.display_name,
        service_principal.publisher_name,
        service_principal.verified_publisher_name,
    ]

    combined = " ".join(
        value.lower()
        for value in values
        if isinstance(value, str)
    )

    return any(marker in combined for marker in FIRST_PARTY_MARKERS)


def _permission_context_evidence(
    *,
    permission: str,
    permission_type: str,
    consent_scope: str,
    resource: str,
) -> EvidenceItem:
    item = PERMISSION_RISKS.get(permission, {})

    blast_radius = item.get(
        "blast_radius",
        "Not classified",
    )

    impact = item.get(
        "impact",
        "No impact explanation available.",
    )

    return EvidenceItem(
        evidence_type="permission_context",
        source_table="permission_risk_catalog",
        source_external_id=permission,
        label=f"Permission blast-radius assessment: {permission}",
        detail=(
            f"permission_type={permission_type}; "
            f"consent_scope={consent_scope}; "
            f"resource={resource}; "
            f"blast_radius={blast_radius}; "
            f"impact={impact}"
        ),
        raw_reference={
            "permission": permission,
            "permission_type": permission_type,
            "consent_scope": consent_scope,
            "resource": resource,
            "blast_radius": blast_radius,
            "impact": impact,
        },
    )


def _serialize_evidence(
    evidence: FindingEvidence,
) -> dict[str, Any]:
    return {
        "id": str(evidence.id),
        "evidence_type": evidence.evidence_type,
        "source_table": evidence.source_table,
        "source_external_id": evidence.source_external_id,
        "label": evidence.label,
        "detail": evidence.detail,
        "observed_at": (
            evidence.observed_at.isoformat()
            if evidence.observed_at
            else None
        ),
        "correlation_id": evidence.correlation_id,
        "raw_reference": evidence.raw_reference,
    }


def serialize_finding(
    db: Session,
    finding: Finding,
) -> dict[str, Any]:
    evidence_rows = db.scalars(
        select(FindingEvidence)
        .where(FindingEvidence.finding_id == finding.id)
        .order_by(FindingEvidence.observed_at.asc().nulls_last())
    ).all()

    return {
        "id": str(finding.id),
        "import_run_id": str(finding.import_run_id),
        "case_id": str(finding.case_id) if finding.case_id else None,
        "rule_id": finding.rule_id,
        "title": finding.title,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "disposition": finding.disposition,
        "subject_type": finding.subject_type,
        "subject_external_id": finding.subject_external_id,
        "rationale": finding.rationale,
        "missing_data_notes": finding.missing_data_notes,
        "benign_verification_steps": finding.benign_verification_steps,
        "created_at": (
            finding.created_at.isoformat()
            if finding.created_at
            else None
        ),
        "evidence": [
            _serialize_evidence(evidence)
            for evidence in evidence_rows
        ],
    }


def list_findings(
    db: Session,
    import_run_id: Any,
    severity: str | None = None,
) -> list[dict[str, Any]]:
    statement = (
        select(Finding)
        .where(Finding.import_run_id == import_run_id)
        .order_by(Finding.created_at.desc(), Finding.severity.desc())
    )

    if severity:
        statement = statement.where(Finding.severity == severity)

    findings = db.scalars(statement).all()

    return [
        serialize_finding(db, finding)
        for finding in findings
    ]


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
    suppressions = db.scalars(
        select(SuppressionDecision)
        .where(SuppressionDecision.import_run_id == import_run_id)
        .order_by(SuppressionDecision.subject_display_name.asc())
    ).all()

    return [
        serialize_suppression(suppression)
        for suppression in suppressions
    ]


def _persist_finding(
    db: Session,
    *,
    import_run_id: Any,
    rule_id: str,
    title: str,
    severity: str,
    confidence: str,
    subject_type: str,
    subject_external_id: str,
    rationale: str,
    evidence_items: list[EvidenceItem],
    missing_data_notes: list[str] | None = None,
    benign_verification_steps: list[str] | None = None,
) -> Finding:
    finding = Finding(
        import_run_id=import_run_id,
        rule_id=rule_id,
        title=title,
        severity=severity,
        confidence=confidence,
        disposition="needs_review",
        subject_type=subject_type,
        subject_external_id=subject_external_id,
        rationale=rationale,
        missing_data_notes=missing_data_notes or [],
        benign_verification_steps=benign_verification_steps or [],
    )

    db.add(finding)
    db.flush()

    for item in evidence_items:
        db.add(
            FindingEvidence(
                finding_id=finding.id,
                evidence_type=item.evidence_type,
                source_table=item.source_table,
                source_external_id=item.source_external_id,
                label=item.label,
                detail=item.detail,
                observed_at=item.observed_at,
                correlation_id=item.correlation_id,
                raw_reference=item.raw_reference,
            )
        )

    return finding


def _persist_suppression(
    db: Session,
    *,
    import_run_id: Any,
    subject_external_id: str,
    subject_display_name: str,
    reason: str,
    context: dict[str, Any],
) -> None:
    db.add(
        SuppressionDecision(
            import_run_id=import_run_id,
            subject_type="service_principal",
            subject_external_id=subject_external_id,
            subject_display_name=subject_display_name,
            suppression_code="GS-BASELINE-001",
            reason=reason,
            context=context,
        )
    )


def _grant_evidence(
    grant: OAuthPermissionGrant,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_type="permission_grant",
        source_table="oauth_permission_grants",
        source_external_id=grant.grant_external_id,
        label="Delegated permission grant",
        detail=(
            f"consentType={grant.consent_type}; "
            f"scope={grant.scope or 'not recorded'}"
        ),
        raw_reference=grant.raw_data,
    )


def _assignment_evidence(
    assignment: AppRoleAssignment,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_type="app_role_assignment",
        source_table="app_role_assignments",
        source_external_id=assignment.assignment_external_id,
        label="Application permission assignment",
        detail=(
            f"appRole={_app_role_value(assignment) or 'not resolved'}; "
            f"resource={assignment.resource_display_name or 'not recorded'}"
        ),
        observed_at=assignment.created_datetime,
        raw_reference=assignment.raw_data,
    )


def _credential_evidence(
    credential: Credential,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_type="credential",
        source_table="credentials",
        source_external_id=credential.credential_external_id,
        label="Application or service-principal credential",
        detail=(
            f"type={credential.credential_type or 'unknown'}; "
            f"start={credential.start_datetime.isoformat() if credential.start_datetime else 'unknown'}; "
            f"end={credential.end_datetime.isoformat() if credential.end_datetime else 'unknown'}"
        ),
        observed_at=credential.start_datetime,
        raw_reference=credential.raw_data,
    )


def _sign_in_evidence(
    sign_in: SignInEvent,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_type="sign_in",
        source_table="sign_in_events",
        source_external_id=sign_in.sign_in_external_id,
        label="Service-principal or application sign-in",
        detail=(
            f"app={sign_in.app_display_name or 'not recorded'}; "
            f"ip={sign_in.ip_address or 'not recorded'}; "
            f"resource={sign_in.resource_display_name or 'not recorded'}"
        ),
        observed_at=sign_in.created_datetime,
        correlation_id=sign_in.correlation_id,
        raw_reference=sign_in.raw_data,
    )


def _audit_evidence(
    audit: DirectoryAuditEvent,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_type="directory_audit",
        source_table="directory_audit_events",
        source_external_id=audit.audit_external_id,
        label=audit.activity_display_name or "Directory audit activity",
        detail=(
            f"category={audit.category or 'not recorded'}; "
            f"result={audit.result or 'not recorded'}; "
            f"initiated_by={audit.initiated_by_display_name or 'not recorded'}"
        ),
        observed_at=audit.activity_datetime,
        correlation_id=audit.correlation_id,
        raw_reference=audit.raw_data,
    )


def _owner_evidence(
    owner: Ownership,
    owner_scope: str,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_type="ownership",
        source_table="ownerships",
        source_external_id=owner.owner_external_id,
        label=f"{owner_scope} owner",
        detail=(
            f"owner={owner.owner_display_name or owner.owner_user_principal_name or owner.owner_external_id}; "
            f"account_enabled={owner.owner_account_enabled}"
        ),
        raw_reference=owner.raw_data,
    )


def _credential_time(
    credential: Credential,
    audits_by_external_id: dict[str, DirectoryAuditEvent],
) -> tuple[datetime | None, DirectoryAuditEvent | None]:
    audit = (
        audits_by_external_id.get(
            credential.created_from_audit_event_id
        )
        if credential.created_from_audit_event_id
        else None
    )

    if audit and audit.activity_datetime:
        return audit.activity_datetime, audit

    return credential.start_datetime, audit


def _reference_time(
    audits: list[DirectoryAuditEvent],
    sign_ins: list[SignInEvent],
) -> datetime | None:
    observed_times = [
        item.activity_datetime
        for item in audits
        if item.activity_datetime
    ] + [
        item.created_datetime
        for item in sign_ins
        if item.created_datetime
    ]

    if not observed_times:
        return None

    return max(observed_times)


def _recent_risky_change(
    audits: list[DirectoryAuditEvent],
    reference_time: datetime | None,
) -> tuple[bool, list[DirectoryAuditEvent]]:
    if not reference_time:
        return False, []

    threshold = reference_time - timedelta(days=30)

    suspicious_terms = (
        "consent",
        "credential",
        "secret",
        "certificate",
        "app role",
        "assignment",
        "add application",
        "update application",
        "add service principal",
    )

    matches: list[DirectoryAuditEvent] = []

    for audit in audits:
        if not audit.activity_datetime:
            continue

        if audit.activity_datetime < threshold:
            continue

        activity = (
            audit.activity_display_name or ""
        ).lower()

        if any(term in activity for term in suspicious_terms):
            matches.append(audit)

    return bool(matches), matches


def _suspicious_signins(
    sign_ins: list[SignInEvent],
) -> list[SignInEvent]:
    suspicious: list[SignInEvent] = []

    for sign_in in sign_ins:
        risk = (sign_in.risk_level or "").lower()
        conditional_access = (
            sign_in.conditional_access_status or ""
        ).lower()

        if risk in {
            "medium",
            "high",
            "hidden",
            "at risk",
            "at_risk",
        }:
            suspicious.append(sign_in)
            continue

        if conditional_access in {"failure", "failed"}:
            suspicious.append(sign_in)

    return suspicious


def analyze_import_run(
    db: Session,
    import_run_id: Any,
) -> dict[str, Any]:
    import_run = db.get(ImportRun, import_run_id)

    if not import_run:
        raise ValueError("Import run was not found.")

    previous_finding_ids = list(
        db.scalars(
            select(Finding.id).where(
                Finding.import_run_id == import_run.id
            )
        ).all()
    )

    if previous_finding_ids:
        db.execute(
            delete(FindingEvidence).where(
                FindingEvidence.finding_id.in_(previous_finding_ids)
            )
        )

        db.execute(
            delete(Finding).where(
                Finding.id.in_(previous_finding_ids)
            )
        )

    db.execute(
        delete(SuppressionDecision).where(
            SuppressionDecision.import_run_id == import_run.id
        )
    )

    db.commit()

    applications = db.scalars(
        select(Application).where(
            Application.import_run_id == import_run.id
        )
    ).all()

    service_principals = db.scalars(
        select(ServicePrincipal).where(
            ServicePrincipal.import_run_id == import_run.id
        )
    ).all()

    owners = db.scalars(
        select(Ownership).where(
            Ownership.import_run_id == import_run.id
        )
    ).all()

    credentials = db.scalars(
        select(Credential).where(
            Credential.import_run_id == import_run.id
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

    audits = db.scalars(
        select(DirectoryAuditEvent).where(
            DirectoryAuditEvent.import_run_id == import_run.id
        )
    ).all()

    sign_ins = db.scalars(
        select(SignInEvent).where(
            SignInEvent.import_run_id == import_run.id
        )
    ).all()

    reference_time = _reference_time(audits, sign_ins)

    applications_by_external_id = {
        application.external_id: application
        for application in applications
    }

    applications_by_app_id = {
        application.app_id: application
        for application in applications
        if application.app_id
    }

    service_principals_by_app_id: dict[
        str,
        list[ServicePrincipal],
    ] = defaultdict(list)

    for service_principal in service_principals:
        if service_principal.app_id:
            service_principals_by_app_id[
                service_principal.app_id
            ].append(service_principal)

    owners_by_subject: dict[
        tuple[str, str],
        list[Ownership],
    ] = defaultdict(list)

    for owner in owners:
        owners_by_subject[
            (
                _normalize_resource_type(owner.resource_type),
                owner.resource_external_id,
            )
        ].append(owner)

    grants_by_client_sp: dict[
        str,
        list[OAuthPermissionGrant],
    ] = defaultdict(list)

    for grant in grants:
        if grant.client_service_principal_id:
            grants_by_client_sp[
                grant.client_service_principal_id
            ].append(grant)

    assignments_by_principal: dict[
        str,
        list[AppRoleAssignment],
    ] = defaultdict(list)

    for assignment in assignments:
        if assignment.principal_id:
            assignments_by_principal[
                assignment.principal_id
            ].append(assignment)

    sign_ins_by_sp: dict[
        str,
        list[SignInEvent],
    ] = defaultdict(list)

    for sign_in in sign_ins:
        if sign_in.service_principal_id:
            sign_ins_by_sp[
                sign_in.service_principal_id
            ].append(sign_in)

    for sign_in_group in sign_ins_by_sp.values():
        sign_in_group.sort(
            key=lambda item: (
                item.created_datetime
                or datetime.min.replace(tzinfo=timezone.utc)
            )
        )

    audits_by_external_id = {
        audit.audit_external_id: audit
        for audit in audits
        if audit.audit_external_id
    }

    audits_by_target: dict[
        str,
        list[DirectoryAuditEvent],
    ] = defaultdict(list)

    for audit in audits:
        for target_id in _audit_targets(audit):
            audits_by_target[target_id].append(audit)

    credentials_by_sp: dict[
        str,
        list[Credential],
    ] = defaultdict(list)

    for credential in credentials:
        resource_type = _normalize_resource_type(
            credential.resource_type
        )

        if resource_type in {"serviceprincipal", "serviceprincipals"}:
            credentials_by_sp[
                credential.resource_external_id
            ].append(credential)
            continue

        if resource_type in {"application", "applications"}:
            application = applications_by_external_id.get(
                credential.resource_external_id
            )

            if application and application.app_id:
                for service_principal in service_principals_by_app_id.get(
                    application.app_id,
                    [],
                ):
                    credentials_by_sp[
                        service_principal.external_id
                    ].append(credential)

    for grant in grants:
        matched_permissions, score = _permission_assessment(
            grant.scope
        )

        if (
            (grant.consent_type or "").lower() == "allprincipals"
            and score >= 3
        ):
            service_principal = next(
                (
                    item
                    for item in service_principals
                    if item.external_id
                    == grant.client_service_principal_id
                ),
                None,
            )

            subject_name = (
                service_principal.display_name
                if service_principal
                and service_principal.display_name
                else grant.client_service_principal_id
                or "Unknown application"
            )

            evidence_items = [_grant_evidence(grant)]

            for permission in matched_permissions:
                evidence_items.append(
                    _permission_context_evidence(
                        permission=permission,
                        permission_type="delegated",
                        consent_scope="tenant-wide (AllPrincipals)",
                        resource="Microsoft Graph or imported resource API",
                    )
                )

            _persist_finding(
                db,
                import_run_id=import_run.id,
                rule_id="GS-OAUTH-001",
                title=(
                    "Tenant-wide consent grants sensitive access: "
                    f"{subject_name}"
                ),
                severity="high" if score >= 4 else "medium",
                confidence="medium",
                subject_type="service_principal",
                subject_external_id=(
                    grant.client_service_principal_id
                    or "unknown-service-principal"
                ),
                rationale=(
                    "The grant applies to AllPrincipals, representing "
                    "tenant-wide delegated consent rather than one user. "
                    f"Sensitive delegated permissions detected: "
                    f"{', '.join(matched_permissions)}."
                ),
                evidence_items=evidence_items,
                missing_data_notes=[
                    "The import does not prove whether the consent followed an approved change process."
                ],
                benign_verification_steps=[
                    "Confirm a documented business owner and approval record for the application.",
                    "Verify every delegated permission is required for the stated business workflow.",
                    "Confirm the publisher, support channel, and expected sign-in pattern.",
                ],
            )

    suppression_count = 0

    for service_principal in service_principals:
        related_grants = grants_by_client_sp.get(
            service_principal.external_id,
            [],
        )

        related_assignments = assignments_by_principal.get(
            service_principal.external_id,
            [],
        )

        related_credentials = credentials_by_sp.get(
            service_principal.external_id,
            [],
        )

        related_sign_ins = sign_ins_by_sp.get(
            service_principal.external_id,
            [],
        )

        linked_application = (
            applications_by_app_id.get(service_principal.app_id)
            if service_principal.app_id
            else None
        )

        related_audits: list[DirectoryAuditEvent] = list(
            audits_by_target.get(
                service_principal.external_id,
                [],
            )
        )

        if linked_application:
            related_audits.extend(
                audits_by_target.get(
                    linked_application.external_id,
                    [],
                )
            )

        related_audits = list(
            {
                audit.id: audit
                for audit in related_audits
            }.values()
        )

        permission_scores: list[int] = []
        permission_names: list[str] = []

        for grant in related_grants:
            matched, score = _permission_assessment(grant.scope)
            permission_scores.append(score)
            permission_names.extend(matched)

        for assignment in related_assignments:
            matched, score = _permission_assessment(
                _app_role_value(assignment)
            )
            permission_scores.append(score)
            permission_names.extend(matched)

        max_permission_score = max(permission_scores, default=0)

        subject_name = (
            service_principal.display_name
            or service_principal.external_id
        )

        service_principal_owners = owners_by_subject.get(
            (
                "serviceprincipal",
                service_principal.external_id,
            ),
            [],
        )

        application_owners: list[Ownership] = []

        if linked_application:
            application_owners = owners_by_subject.get(
                (
                    "application",
                    linked_application.external_id,
                ),
                [],
            )

        all_owners = (
            service_principal_owners
            + application_owners
        )

        active_owners = [
            owner
            for owner in all_owners
            if owner.owner_account_enabled is True
        ]

        is_tenant_owned = (
            bool(service_principal.app_owner_organization_id)
            and service_principal.app_owner_organization_id
            == import_run.tenant_id
        )

        is_external = (
            bool(service_principal.app_owner_organization_id)
            and service_principal.app_owner_organization_id
            != import_run.tenant_id
        )

        is_unverified = not (
            service_principal.verified_publisher_id
            or service_principal.verified_publisher_name
        )

        has_recent_change, recent_audits = _recent_risky_change(
            related_audits,
            reference_time,
        )

        suspicious_sign_ins = _suspicious_signins(
            related_sign_ins
        )

        has_credentials = bool(related_credentials)

        material_risk = any(
            [
                max_permission_score >= 3,
                has_credentials,
                has_recent_change,
                bool(suspicious_sign_ins),
            ]
        )

        baseline_external_app = (
            is_external
            and not is_tenant_owned
            and not material_risk
            and (not active_owners or is_unverified)
        )

        if baseline_external_app:
            baseline_label = (
                "likely first-party context"
                if _likely_first_party(service_principal)
                else "external enterprise application context"
            )

            _persist_suppression(
                db,
                import_run_id=import_run.id,
                subject_external_id=service_principal.external_id,
                subject_display_name=subject_name,
                reason=(
                    "Suppressed from the investigation queue because this "
                    f"appears to be normal {baseline_label}: no sensitive "
                    "delegated or application permissions were resolved, "
                    "no credential metadata was present, no recent identity "
                    "change was observed, and no elevated sign-in risk was "
                    "present in imported telemetry. Owner and publisher gaps "
                    "remain inventory context, not standalone incident evidence."
                ),
                context={
                    "is_external": is_external,
                    "likely_first_party": _likely_first_party(
                        service_principal
                    ),
                    "active_owner_present": bool(active_owners),
                    "verified_publisher_present": not is_unverified,
                    "max_permission_score": max_permission_score,
                    "credential_count": len(related_credentials),
                    "recent_identity_change": has_recent_change,
                    "suspicious_signin_count": len(
                        suspicious_sign_ins
                    ),
                },
            )

            suppression_count += 1

        owner_case_threshold = (
            is_tenant_owned
            or material_risk
        )

        if not active_owners and owner_case_threshold:
            evidence_items: list[EvidenceItem] = []

            for owner in service_principal_owners:
                evidence_items.append(
                    _owner_evidence(
                        owner,
                        "Service-principal",
                    )
                )

            for owner in application_owners:
                evidence_items.append(
                    _owner_evidence(
                        owner,
                        "Linked application",
                    )
                )

            for audit in recent_audits[:2]:
                evidence_items.append(_audit_evidence(audit))

            if not evidence_items:
                evidence_items = [
                    EvidenceItem(
                        evidence_type="inventory_state",
                        source_table="service_principals",
                        source_external_id=service_principal.external_id,
                        label="No active owner in imported inventory",
                        detail=(
                            "No active owner record was supplied for either "
                            "the service principal or linked application."
                        ),
                        raw_reference=service_principal.raw_data,
                    )
                ]

            owner_context: list[str] = []

            if is_tenant_owned:
                owner_context.append(
                    "the service principal is tenant-owned"
                )

            if max_permission_score >= 3:
                owner_context.append(
                    "it has sensitive permissions"
                )

            if has_credentials:
                owner_context.append(
                    "credential metadata is present"
                )

            if has_recent_change:
                owner_context.append(
                    "recent identity-management activity was observed"
                )

            if suspicious_sign_ins:
                owner_context.append(
                    "elevated sign-in risk was observed"
                )

            _persist_finding(
                db,
                import_run_id=import_run.id,
                rule_id="GS-OWNER-001",
                title=f"No active owner recorded for: {subject_name}",
                severity=(
                    "high"
                    if max_permission_score >= 4
                    else "medium"
                ),
                confidence=(
                    "high"
                    if all_owners
                    else "medium"
                ),
                subject_type="service_principal",
                subject_external_id=service_principal.external_id,
                rationale=(
                    "No active accountable owner was found across imported "
                    "service-principal and linked-application ownership "
                    "records. This is case-worthy because "
                    + (
                        "; ".join(owner_context)
                        if owner_context
                        else "the imported evidence requires ownership validation"
                    )
                    + "."
                ),
                evidence_items=evidence_items,
                missing_data_notes=[
                    "Owner records can be incomplete when exports omit application or service-principal ownership."
                ],
                benign_verification_steps=[
                    "Confirm the responsible application owner and service owner.",
                    "Verify the owner account is active and can approve credential rotation or removal.",
                    "Check whether the application is documented in the tenant application register.",
                ],
            )

        publisher_case_threshold = material_risk

        if (
            is_external
            and is_unverified
            and publisher_case_threshold
        ):
            evidence_items = [
                EvidenceItem(
                    evidence_type="inventory_state",
                    source_table="service_principals",
                    source_external_id=service_principal.external_id,
                    label="External, unverified publisher state",
                    detail=(
                        f"app_owner_organization_id={service_principal.app_owner_organization_id}; "
                        "verified publisher metadata was not present."
                    ),
                    raw_reference=service_principal.raw_data,
                )
            ]

            for audit in recent_audits[:2]:
                evidence_items.append(_audit_evidence(audit))

            _persist_finding(
                db,
                import_run_id=import_run.id,
                rule_id="GS-PUBLISHER-001",
                title=(
                    "External service principal has no verified publisher: "
                    f"{subject_name}"
                ),
                severity=(
                    "high"
                    if max_permission_score >= 4
                    else "medium"
                ),
                confidence="low",
                subject_type="service_principal",
                subject_external_id=service_principal.external_id,
                rationale=(
                    "The service principal appears externally owned and "
                    "does not include verified-publisher metadata. This "
                    "became case-worthy only because material risk context "
                    "was also observed, such as sensitive permissions, "
                    "credentials, recent identity change, or elevated sign-in risk."
                ),
                evidence_items=evidence_items,
                missing_data_notes=[
                    "Publisher verification is not a malware or reputation verdict."
                ],
                benign_verification_steps=[
                    "Confirm the vendor and support channel through procurement or the application owner.",
                    "Validate the app ID, permissions, and publisher against vendor documentation.",
                    "Confirm the application is expected in this tenant.",
                ],
            )

        for assignment in related_assignments:
            app_role_value = _app_role_value(assignment)
            matched_permissions, score = _permission_assessment(
                app_role_value
            )

            if score < 4:
                continue

            evidence_items = [_assignment_evidence(assignment)]

            for permission in matched_permissions:
                evidence_items.append(
                    _permission_context_evidence(
                        permission=permission,
                        permission_type="application",
                        consent_scope="tenant-wide application permission",
                        resource=(
                            assignment.resource_display_name
                            or "Imported resource API"
                        ),
                    )
                )

            _persist_finding(
                db,
                import_run_id=import_run.id,
                rule_id="GS-ROLE-001",
                title=(
                    "Privileged application permission assigned: "
                    f"{subject_name}"
                ),
                severity="high",
                confidence="medium",
                subject_type="service_principal",
                subject_external_id=service_principal.external_id,
                rationale=(
                    "The service principal has a high-impact application "
                    f"permission: {', '.join(matched_permissions)}. "
                    "This is tenant-level application access, not user-scoped delegated consent."
                ),
                evidence_items=evidence_items,
                missing_data_notes=[
                    "The assignment export may not show the approval path or original change ticket."
                ],
                benign_verification_steps=[
                    "Confirm the permission is documented and required for the service function.",
                    "Validate the assignee, resource, and app role against the approved architecture.",
                    "Review whether a lower-privilege permission model is available.",
                ],
            )

        for credential in related_credentials:
            if not credential.start_datetime or not credential.end_datetime:
                continue

            lifetime_days = (
                credential.end_datetime
                - credential.start_datetime
            ).days

            if lifetime_days <= 365:
                continue

            _, related_audit = _credential_time(
                credential,
                audits_by_external_id,
            )

            evidence_items = [_credential_evidence(credential)]

            if related_audit:
                evidence_items.append(_audit_evidence(related_audit))

            _persist_finding(
                db,
                import_run_id=import_run.id,
                rule_id="GS-CRED-001",
                title=(
                    f"Excessive credential lifetime on: {subject_name}"
                ),
                severity=(
                    "high"
                    if lifetime_days >= 730
                    else "medium"
                ),
                confidence="medium",
                subject_type="service_principal",
                subject_external_id=service_principal.external_id,
                rationale=(
                    f"The credential lifetime is {lifetime_days} days. "
                    "Long-lived application secrets or certificates increase "
                    "the persistence window if a credential is exposed."
                ),
                evidence_items=evidence_items,
                missing_data_notes=[
                    "The export contains credential metadata only; GrantScope never receives secret material."
                ],
                benign_verification_steps=[
                    "Verify the credential lifetime against the organization's rotation standard.",
                    "Confirm the credential has a documented owner and rotation process.",
                    "Determine whether workload identity federation can replace a long-lived secret.",
                ],
            )

        for credential in related_credentials:
            credential_time, related_audit = _credential_time(
                credential,
                audits_by_external_id,
            )

            if not credential_time or max_permission_score < 4:
                continue

            evidence_items = [_credential_evidence(credential)]

            if related_audit:
                evidence_items.append(_audit_evidence(related_audit))

            _persist_finding(
                db,
                import_run_id=import_run.id,
                rule_id="GS-CRED-002",
                title=(
                    "Credential present on privileged service principal: "
                    f"{subject_name}"
                ),
                severity="high",
                confidence=(
                    "medium"
                    if related_audit
                    else "low"
                ),
                subject_type="service_principal",
                subject_external_id=service_principal.external_id,
                rationale=(
                    "A credential is associated with a service principal "
                    f"that also has high-impact permissions: "
                    f"{', '.join(sorted(set(permission_names)))}. "
                    "This combination increases persistence and blast-radius risk."
                ),
                evidence_items=evidence_items,
                missing_data_notes=[
                    "Credential creation time is inferred from audit linkage when available, otherwise from credential start time."
                ],
                benign_verification_steps=[
                    "Confirm the credential was created through an approved deployment or rotation process.",
                    "Validate the owner and exact workload using the credential.",
                    "Review whether the privileged permissions are still required.",
                ],
            )

            recent_privileged_assignment = next(
                (
                    assignment
                    for assignment in related_assignments
                    if assignment.created_datetime
                    and assignment.created_datetime <= credential_time
                    and assignment.created_datetime
                    >= credential_time - timedelta(hours=24)
                    and _permission_assessment(
                        _app_role_value(assignment)
                    )[1] >= 4
                ),
                None,
            )

            first_use_after_credential = next(
                (
                    sign_in
                    for sign_in in related_sign_ins
                    if sign_in.created_datetime
                    and sign_in.created_datetime >= credential_time
                    and sign_in.created_datetime
                    <= credential_time + timedelta(minutes=60)
                ),
                None,
            )

            if not recent_privileged_assignment:
                continue

            if not first_use_after_credential:
                continue

            sequence_evidence = [
                _assignment_evidence(recent_privileged_assignment),
                _credential_evidence(credential),
                _sign_in_evidence(first_use_after_credential),
            ]

            if related_audit:
                sequence_evidence.append(_audit_evidence(related_audit))

            _persist_finding(
                db,
                import_run_id=import_run.id,
                rule_id="GS-SEQUENCE-001",
                title=(
                    "Credential addition followed by rapid privileged use: "
                    f"{subject_name}"
                ),
                severity="critical",
                confidence="high",
                subject_type="service_principal",
                subject_external_id=service_principal.external_id,
                rationale=(
                    "The imported evidence shows a high-impact application "
                    "permission assigned within 24 hours before a credential "
                    "event, followed by service-principal use within 60 minutes "
                    "of the credential event. This sequence is consistent with "
                    "a persistence or privilege-abuse path and requires immediate human review."
                ),
                evidence_items=sequence_evidence,
                missing_data_notes=[
                    "Timing correlation is based on imported audit and sign-in records; missing retention periods can reduce certainty."
                ],
                benign_verification_steps=[
                    "Validate the change ticket, deployment pipeline, and operator responsible for the role assignment and credential action.",
                    "Confirm the immediate sign-in IP, resource, and workload are expected.",
                    "Review whether the credential and privileged assignment should be revoked or rotated pending investigation.",
                ],
            )

    db.commit()

    findings = db.scalars(
        select(Finding)
        .where(Finding.import_run_id == import_run.id)
        .order_by(Finding.created_at.desc())
    ).all()

    severity_counts = Counter(
        finding.severity
        for finding in findings
    )

    return {
        "import_run_id": str(import_run.id),
        "analysis_status": "completed",
        "finding_count": len(findings),
        "suppression_count": suppression_count,
        "severity_counts": dict(severity_counts),
        "findings": [
            serialize_finding(db, finding)
            for finding in findings
        ],
    }