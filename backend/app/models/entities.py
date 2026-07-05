import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, default="bundle_zip")
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bundle_schema_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="processing")
    evidence_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ImportedArtifact(Base):
    __tablename__ = "imported_artifacts"
    __table_args__ = (
        Index("ix_imported_artifacts_run_file", "import_run_id", "file_name", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        Index("ix_applications_run_external", "import_run_id", "external_id", unique=True),
        Index("ix_applications_run_app_id", "import_run_id", "app_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    app_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sign_in_audience: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publisher_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_publisher_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_publisher_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    disabled_by_microsoft_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class ServicePrincipal(Base):
    __tablename__ = "service_principals"
    __table_args__ = (
        Index("ix_service_principals_run_external", "import_run_id", "external_id", unique=True),
        Index("ix_service_principals_run_app_id", "import_run_id", "app_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    app_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    service_principal_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    account_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    app_owner_organization_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publisher_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_publisher_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_publisher_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tags: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class Ownership(Base):
    __tablename__ = "ownerships"
    __table_args__ = (
        Index("ix_ownerships_run_resource", "import_run_id", "resource_type", "resource_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    owner_user_principal_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    owner_account_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class Credential(Base):
    __tablename__ = "credentials"
    __table_args__ = (
        Index(
            "ix_credentials_run_resource",
            "import_run_id",
            "resource_type",
            "resource_external_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    credential_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credential_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    key_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_from_audit_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class OAuthPermissionGrant(Base):
    __tablename__ = "oauth_permission_grants"
    __table_args__ = (
        Index("ix_oauth_grants_run_client", "import_run_id", "client_service_principal_id"),
        Index("ix_oauth_grants_run_resource", "import_run_id", "resource_service_principal_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    grant_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_service_principal_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_service_principal_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    principal_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consent_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class AppRoleAssignment(Base):
    __tablename__ = "app_role_assignments"
    __table_args__ = (
        Index("ix_app_role_assignments_run_principal", "import_run_id", "principal_id"),
        Index("ix_app_role_assignments_run_resource", "import_run_id", "resource_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    assignment_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    app_role_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    principal_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    principal_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    principal_display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class DirectoryAuditEvent(Base):
    __tablename__ = "directory_audit_events"
    __table_args__ = (
        Index("ix_directory_audits_run_activity", "import_run_id", "activity_datetime"),
        Index("ix_directory_audits_run_correlation", "import_run_id", "correlation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    audit_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activity_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activity_display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[str | None] = mapped_column(String(100), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    initiated_by_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    initiated_by_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    initiated_by_display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    target_resources: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    additional_details: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class SignInEvent(Base):
    __tablename__ = "sign_in_events"
    __table_args__ = (
        Index("ix_sign_in_events_run_created", "import_run_id", "created_datetime"),
        Index("ix_sign_in_events_run_correlation", "import_run_id", "correlation_id"),
        Index("ix_sign_in_events_run_service_principal", "import_run_id", "service_principal_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sign_in_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    app_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    app_display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    service_principal_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    service_principal_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_principal_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conditional_access_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status_detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    location_detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    device_detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class InvestigationCase(Base):
    __tablename__ = "investigation_cases"
    __table_args__ = (
        Index("ix_cases_run_status", "import_run_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(100), nullable=False, default="open")
    severity: Mapped[str] = mapped_column(String(50), nullable=False, default="medium")
    confidence: Mapped[str] = mapped_column(String(50), nullable=False, default="low")
    disposition: Mapped[str] = mapped_column(String(100), nullable=False, default="needs_review")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        Index("ix_findings_run_severity", "import_run_id", "severity"),
        Index("ix_findings_case", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    import_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("investigation_cases.id", ondelete="SET NULL"),
        nullable=True,
    )
    rule_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[str] = mapped_column(String(50), nullable=False)
    disposition: Mapped[str] = mapped_column(String(100), nullable=False, default="needs_review")
    subject_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    missing_data_notes: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    benign_verification_steps: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )


class CaseEvidence(Base):
    __tablename__ = "case_evidence"
    __table_args__ = (
        Index("ix_case_evidence_case", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("investigation_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_table: Mapped[str] = mapped_column(String(100), nullable=False)
    source_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_reference: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)