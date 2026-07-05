from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.entities import (
    CaseEvidence,
    Finding,
    ImportRun,
    InvestigationCase,
    ServicePrincipal,
)
from app.models.finding_evidence import FindingEvidence
from app.services.analysis_engine import serialize_finding


SEVERITY_RANK = {
    "informational": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

CONFIDENCE_RANK = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


def _highest(values: list[str], ranking: dict[str, int], fallback: str) -> str:
    if not values:
        return fallback

    return max(values, key=lambda value: ranking.get(value, 0))


def _resolve_subject_name(
    db: Session,
    import_run_id: Any,
    subject_type: str,
    subject_external_id: str,
) -> str:
    if subject_type == "service_principal":
        service_principal = db.scalar(
            select(ServicePrincipal).where(
                ServicePrincipal.import_run_id == import_run_id,
                ServicePrincipal.external_id == subject_external_id,
            )
        )

        if service_principal and service_principal.display_name:
            return service_principal.display_name

    return subject_external_id


def _case_summary(
    subject_name: str,
    findings: list[Finding],
    severity: str,
    confidence: str,
) -> str:
    ordered_findings = sorted(
        findings,
        key=lambda finding: (
            SEVERITY_RANK.get(finding.severity, 0),
            CONFIDENCE_RANK.get(finding.confidence, 0),
        ),
        reverse=True,
    )

    top_titles = [finding.title for finding in ordered_findings[:3]]

    return (
        f"GrantScope grouped {len(findings)} related findings for "
        f"{subject_name}. Overall severity is {severity} with {confidence} "
        f"confidence. Primary investigation signals: "
        + "; ".join(top_titles)
        + "."
    )


def _case_recommendations(case: InvestigationCase) -> list[str]:
    recommendations = [
        "Confirm whether the application, permission grant, credential activity, and recent use were approved through a documented change process.",
        "Validate the accountable service owner, application owner, and business purpose before closing the case.",
        "Review the exact permissions and determine whether a lower-privilege design is possible.",
    ]

    if case.severity in {"high", "critical"}:
        recommendations.insert(
            0,
            "If the activity cannot be validated promptly, consider temporary containment through human-approved service-principal disablement and credential rotation.",
        )

    if case.severity == "critical":
        recommendations.insert(
            1,
            "Prioritize review of the correlated credential event, first-use sign-in, source IP, and related audit initiator.",
        )

    return recommendations


def _serialize_case_evidence(evidence: CaseEvidence) -> dict[str, Any]:
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


def _get_case_findings(db: Session, case_id: Any) -> list[Finding]:
    return db.scalars(
        select(Finding)
        .where(Finding.case_id == case_id)
        .order_by(Finding.created_at.asc())
    ).all()


def _get_case_evidence(db: Session, case_id: Any) -> list[CaseEvidence]:
    return db.scalars(
        select(CaseEvidence)
        .where(CaseEvidence.case_id == case_id)
        .order_by(CaseEvidence.observed_at.asc().nulls_last(), CaseEvidence.label.asc())
    ).all()


def serialize_case_summary(db: Session, case: InvestigationCase) -> dict[str, Any]:
    findings = _get_case_findings(db, case.id)
    evidence = _get_case_evidence(db, case.id)

    return {
        "id": str(case.id),
        "import_run_id": str(case.import_run_id),
        "title": case.title,
        "status": case.status,
        "severity": case.severity,
        "confidence": case.confidence,
        "disposition": case.disposition,
        "summary": case.summary,
        "finding_count": len(findings),
        "evidence_count": len(evidence),
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
    }


def get_case_detail(
    db: Session,
    case_id: Any,
) -> dict[str, Any] | None:
    case = db.get(InvestigationCase, case_id)

    if not case:
        return None

    findings = _get_case_findings(db, case.id)
    evidence = _get_case_evidence(db, case.id)

    timeline = [
        {
            "observed_at": evidence_item.observed_at.isoformat(),
            "label": evidence_item.label,
            "detail": evidence_item.detail,
            "source_table": evidence_item.source_table,
            "source_external_id": evidence_item.source_external_id,
            "correlation_id": evidence_item.correlation_id,
        }
        for evidence_item in evidence
        if evidence_item.observed_at
    ]

    verification_steps: list[str] = []
    missing_data_notes: list[str] = []

    for finding in findings:
        for step in finding.benign_verification_steps or []:
            if step not in verification_steps:
                verification_steps.append(step)

        for note in finding.missing_data_notes or []:
            if note not in missing_data_notes:
                missing_data_notes.append(note)

    return {
        **serialize_case_summary(db, case),
        "findings": [serialize_finding(db, finding) for finding in findings],
        "evidence": [_serialize_case_evidence(item) for item in evidence],
        "timeline": timeline,
        "what_would_make_this_benign": verification_steps,
        "recommended_human_review_actions": _case_recommendations(case),
        "missing_data_notes": missing_data_notes,
    }


def list_cases(
    db: Session,
    import_run_id: Any,
) -> list[dict[str, Any]]:
    cases = db.scalars(
        select(InvestigationCase)
        .where(InvestigationCase.import_run_id == import_run_id)
        .order_by(InvestigationCase.created_at.desc())
    ).all()

    return [serialize_case_summary(db, case) for case in cases]


def _copy_finding_evidence_to_case(
    db: Session,
    case: InvestigationCase,
    findings: list[Finding],
) -> int:
    finding_ids = [finding.id for finding in findings]

    evidence_rows = db.scalars(
        select(FindingEvidence)
        .where(FindingEvidence.finding_id.in_(finding_ids))
        .order_by(FindingEvidence.observed_at.asc().nulls_last())
    ).all()

    seen: set[tuple[Any, ...]] = set()
    copied_count = 0

    for evidence in evidence_rows:
        dedupe_key = (
            evidence.source_table,
            evidence.source_external_id,
            evidence.label,
            evidence.detail,
            evidence.observed_at,
            evidence.correlation_id,
        )

        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)

        db.add(
            CaseEvidence(
                case_id=case.id,
                evidence_type=evidence.evidence_type,
                source_table=evidence.source_table,
                source_external_id=evidence.source_external_id,
                label=evidence.label,
                detail=evidence.detail,
                observed_at=evidence.observed_at,
                correlation_id=evidence.correlation_id,
                raw_reference=evidence.raw_reference,
            )
        )

        copied_count += 1

    return copied_count


def generate_cases_for_import_run(
    db: Session,
    import_run_id: Any,
) -> dict[str, Any]:
    import_run = db.get(ImportRun, import_run_id)

    if not import_run:
        raise ValueError("Import run was not found.")

    existing_cases = db.scalars(
        select(InvestigationCase).where(
            InvestigationCase.import_run_id == import_run.id
        )
    ).all()

    existing_case_ids = [case.id for case in existing_cases]

    if existing_case_ids:
        db.execute(
            update(Finding)
            .where(Finding.import_run_id == import_run.id)
            .values(case_id=None)
        )

        db.execute(
            delete(CaseEvidence).where(
                CaseEvidence.case_id.in_(existing_case_ids)
            )
        )

        db.execute(
            delete(InvestigationCase).where(
                InvestigationCase.id.in_(existing_case_ids)
            )
        )

        db.commit()

    findings = db.scalars(
        select(Finding)
        .where(Finding.import_run_id == import_run.id)
        .order_by(Finding.created_at.asc())
    ).all()

    grouped_findings: dict[tuple[str, str], list[Finding]] = defaultdict(list)

    for finding in findings:
        grouped_findings[
            (
                finding.subject_type,
                finding.subject_external_id,
            )
        ].append(finding)

    generated_cases: list[InvestigationCase] = []

    for (subject_type, subject_external_id), subject_findings in grouped_findings.items():
        severity = _highest(
            [finding.severity for finding in subject_findings],
            SEVERITY_RANK,
            "medium",
        )

        confidence = _highest(
            [finding.confidence for finding in subject_findings],
            CONFIDENCE_RANK,
            "low",
        )

        subject_name = _resolve_subject_name(
            db=db,
            import_run_id=import_run.id,
            subject_type=subject_type,
            subject_external_id=subject_external_id,
        )

        investigation_case = InvestigationCase(
            import_run_id=import_run.id,
            title=f"Identity application investigation: {subject_name}",
            status="open",
            severity=severity,
            confidence=confidence,
            disposition="needs_review",
            summary=_case_summary(
                subject_name=subject_name,
                findings=subject_findings,
                severity=severity,
                confidence=confidence,
            ),
        )

        db.add(investigation_case)
        db.flush()

        for finding in subject_findings:
            finding.case_id = investigation_case.id

        _copy_finding_evidence_to_case(
            db=db,
            case=investigation_case,
            findings=subject_findings,
        )

        generated_cases.append(investigation_case)

    db.commit()

    serialized_cases = [
        serialize_case_summary(db, investigation_case)
        for investigation_case in generated_cases
    ]

    return {
        "import_run_id": str(import_run.id),
        "case_generation_status": "completed",
        "case_count": len(serialized_cases),
        "cases": serialized_cases,
    }