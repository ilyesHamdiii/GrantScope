from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AppRoleAssignment,
    Application,
    Credential,
    DirectoryAuditEvent,
    ImportRun,
    ImportedArtifact,
    OAuthPermissionGrant,
    Ownership,
    ServicePrincipal,
    SignInEvent,
)


REQUIRED_JSON_FILES = [
    "manifest.json",
    "applications.json",
    "service_principals.json",
    "owners.json",
    "credentials.json",
    "oauth2_permission_grants.json",
    "app_role_assignments.json",
    "directory_audits.json",
    "sign_ins.json",
]


class BundleValidationError(ValueError):
    pass


def _text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _get(record: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]

    return default


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _boolean(value: Any) -> bool | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()

    if normalized in {"true", "1", "yes"}:
        return True

    if normalized in {"false", "0", "no"}:
        return False

    return None


def _datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    if not isinstance(value, str):
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _required_text(record: dict[str, Any], *keys: str) -> str:
    value = _text(_get(record, *keys))

    if not value:
        joined = ", ".join(keys)
        raise BundleValidationError(f"Record is missing a required field: {joined}")

    return value


def _read_json_member(archive: zipfile.ZipFile, file_name: str) -> Any:
    try:
        raw = archive.read(file_name)
    except KeyError as error:
        raise BundleValidationError(f"Bundle is missing {file_name}") from error

    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleValidationError(f"{file_name} is not valid UTF-8 JSON") from error


def read_bundle_from_zip(raw_bytes: bytes) -> dict[str, Any]:
    if not raw_bytes:
        raise BundleValidationError("The uploaded bundle is empty.")

    archive_buffer = io.BytesIO(raw_bytes)

    if not zipfile.is_zipfile(archive_buffer):
        raise BundleValidationError("The uploaded file must be a .zip evidence bundle.")

    archive_buffer.seek(0)

    with zipfile.ZipFile(archive_buffer) as archive:
        archive_names = set(archive.namelist())
        missing_files = [
            required_file
            for required_file in REQUIRED_JSON_FILES
            if required_file not in archive_names
        ]

        if missing_files:
            missing = ", ".join(missing_files)
            raise BundleValidationError(f"Bundle is missing required files: {missing}")

        payload = {
            file_name: _read_json_member(archive, file_name)
            for file_name in REQUIRED_JSON_FILES
        }

    manifest = payload["manifest.json"]

    if not isinstance(manifest, dict):
        raise BundleValidationError("manifest.json must contain a JSON object.")

    schema_version = _text(manifest.get("schema_version"))

    if schema_version != "1.0":
        raise BundleValidationError(
            "Unsupported bundle schema_version. GrantScope currently requires 1.0."
        )

    for file_name in REQUIRED_JSON_FILES:
        if file_name == "manifest.json":
            continue

        if not isinstance(payload[file_name], list):
            raise BundleValidationError(f"{file_name} must contain a JSON array.")

    tenant = _dict(manifest.get("tenant"))
    tenant_id = _text(tenant.get("tenant_id")) or _text(manifest.get("tenant_id"))

    if not tenant_id:
        raise BundleValidationError(
            "manifest.json must include tenant.tenant_id or tenant_id."
        )

    return payload


def _publisher_values(record: dict[str, Any]) -> tuple[str | None, str | None]:
    verified = _dict(
        _get(
            record,
            "verifiedPublisher",
            "verified_publisher",
        )
    )

    publisher_id = _text(
        _get(
            record,
            "verifiedPublisherId",
            "verified_publisher_id",
            default=verified.get("verifiedPublisherId") or verified.get("id"),
        )
    )

    publisher_name = _text(
        _get(
            record,
            "verifiedPublisherDisplayName",
            "verified_publisher_name",
            default=verified.get("displayName"),
        )
    )

    return publisher_id, publisher_name


def _audit_initiator(record: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    initiated_by = _dict(_get(record, "initiatedBy", "initiated_by"))

    user = _dict(initiated_by.get("user"))
    app = _dict(initiated_by.get("app"))

    if user:
        return (
            "user",
            _text(user.get("id")),
            _text(user.get("displayName")) or _text(user.get("userPrincipalName")),
        )

    if app:
        return (
            "app",
            _text(app.get("servicePrincipalId")) or _text(app.get("appId")),
            _text(app.get("displayName")),
        )

    return (
        _text(_get(record, "initiated_by_type")),
        _text(_get(record, "initiated_by_id")),
        _text(_get(record, "initiated_by_display_name")),
    )


def _artifact_hash(records: Any) -> str:
    serialized = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def serialize_import_run(import_run: ImportRun) -> dict[str, Any]:
    return {
        "id": str(import_run.id),
        "source_name": import_run.source_name,
        "source_type": import_run.source_type,
        "tenant_id": import_run.tenant_id,
        "tenant_display_name": import_run.tenant_display_name,
        "bundle_schema_version": import_run.bundle_schema_version,
        "status": import_run.status,
        "evidence_summary": import_run.evidence_summary,
        "error_message": import_run.error_message,
        "created_at": import_run.created_at.isoformat() if import_run.created_at else None,
        "completed_at": import_run.completed_at.isoformat() if import_run.completed_at else None,
    }


def import_bundle_archive(
    db: Session,
    raw_bytes: bytes,
    source_name: str,
) -> ImportRun:
    payload = read_bundle_from_zip(raw_bytes)
    manifest = payload["manifest.json"]
    tenant = _dict(manifest.get("tenant"))

    tenant_id = _text(tenant.get("tenant_id")) or _text(manifest.get("tenant_id"))
    tenant_display_name = (
        _text(tenant.get("display_name"))
        or _text(tenant.get("displayName"))
        or _text(manifest.get("tenant_display_name"))
    )

    import_run = ImportRun(
        source_name=source_name,
        source_type="bundle_zip",
        tenant_id=tenant_id,
        tenant_display_name=tenant_display_name,
        bundle_schema_version="1.0",
        status="processing",
    )

    db.add(import_run)
    db.flush()

    record_counts: dict[str, int] = {}

    try:
        for file_name in REQUIRED_JSON_FILES:
            if file_name == "manifest.json":
                continue

            records = payload[file_name]
            record_counts[file_name] = len(records)

            db.add(
                ImportedArtifact(
                    import_run_id=import_run.id,
                    file_name=file_name,
                    sha256=_artifact_hash(records),
                    record_count=len(records),
                )
            )

        for record in payload["applications.json"]:
            publisher_id, publisher_name = _publisher_values(record)

            db.add(
                Application(
                    import_run_id=import_run.id,
                    external_id=_required_text(record, "id", "external_id"),
                    app_id=_text(_get(record, "appId", "app_id")),
                    display_name=_text(_get(record, "displayName", "display_name")),
                    created_datetime=_datetime(
                        _get(record, "createdDateTime", "created_datetime")
                    ),
                    sign_in_audience=_text(
                        _get(record, "signInAudience", "sign_in_audience")
                    ),
                    publisher_domain=_text(
                        _get(record, "publisherDomain", "publisher_domain")
                    ),
                    verified_publisher_id=publisher_id,
                    verified_publisher_name=publisher_name,
                    disabled_by_microsoft_status=_text(
                        _get(
                            record,
                            "disabledByMicrosoftStatus",
                            "disabled_by_microsoft_status",
                        )
                    ),
                    raw_data=record,
                )
            )

        for record in payload["service_principals.json"]:
            publisher_id, publisher_name = _publisher_values(record)

            db.add(
                ServicePrincipal(
                    import_run_id=import_run.id,
                    external_id=_required_text(record, "id", "external_id"),
                    app_id=_text(_get(record, "appId", "app_id")),
                    display_name=_text(_get(record, "displayName", "display_name")),
                    service_principal_type=_text(
                        _get(record, "servicePrincipalType", "service_principal_type")
                    ),
                    account_enabled=_boolean(
                        _get(record, "accountEnabled", "account_enabled")
                    ),
                    app_owner_organization_id=_text(
                        _get(
                            record,
                            "appOwnerOrganizationId",
                            "app_owner_organization_id",
                        )
                    ),
                    publisher_name=_text(
                        _get(record, "publisherName", "publisher_name")
                    ),
                    verified_publisher_id=publisher_id,
                    verified_publisher_name=publisher_name,
                    tags=_list(_get(record, "tags")),
                    raw_data=record,
                )
            )

        for record in payload["owners.json"]:
            db.add(
                Ownership(
                    import_run_id=import_run.id,
                    resource_type=_required_text(
                        record,
                        "resource_type",
                        "resourceType",
                    ),
                    resource_external_id=_required_text(
                        record,
                        "resource_id",
                        "resourceId",
                        "resource_external_id",
                    ),
                    owner_external_id=_required_text(
                        record,
                        "owner_id",
                        "ownerId",
                        "owner_external_id",
                    ),
                    owner_type=_text(_get(record, "owner_type", "ownerType")),
                    owner_display_name=_text(
                        _get(record, "owner_display_name", "ownerDisplayName", "displayName")
                    ),
                    owner_user_principal_name=_text(
                        _get(
                            record,
                            "owner_user_principal_name",
                            "ownerUserPrincipalName",
                            "userPrincipalName",
                        )
                    ),
                    owner_account_enabled=_boolean(
                        _get(
                            record,
                            "owner_account_enabled",
                            "ownerAccountEnabled",
                            "accountEnabled",
                        )
                    ),
                    raw_data=record,
                )
            )

        for record in payload["credentials.json"]:
            db.add(
                Credential(
                    import_run_id=import_run.id,
                    resource_type=_required_text(
                        record,
                        "resource_type",
                        "resourceType",
                    ),
                    resource_external_id=_required_text(
                        record,
                        "resource_id",
                        "resourceId",
                        "resource_external_id",
                    ),
                    credential_external_id=_text(
                        _get(record, "id", "credential_id", "credential_external_id")
                    ),
                    credential_type=_text(
                        _get(record, "credential_type", "credentialType", "type")
                    ),
                    display_name=_text(
                        _get(record, "displayName", "display_name")
                    ),
                    key_id=_text(_get(record, "keyId", "key_id")),
                    start_datetime=_datetime(
                        _get(record, "startDateTime", "start_datetime")
                    ),
                    end_datetime=_datetime(
                        _get(record, "endDateTime", "end_datetime")
                    ),
                    created_from_audit_event_id=_text(
                        _get(
                            record,
                            "created_from_audit_event_id",
                            "createdFromAuditEventId",
                        )
                    ),
                    raw_data=record,
                )
            )

        for record in payload["oauth2_permission_grants.json"]:
            db.add(
                OAuthPermissionGrant(
                    import_run_id=import_run.id,
                    grant_external_id=_text(_get(record, "id", "grant_id")),
                    client_service_principal_id=_text(
                        _get(record, "clientId", "client_id")
                    ),
                    resource_service_principal_id=_text(
                        _get(record, "resourceId", "resource_id")
                    ),
                    principal_id=_text(_get(record, "principalId", "principal_id")),
                    consent_type=_text(_get(record, "consentType", "consent_type")),
                    scope=_text(_get(record, "scope")),
                    raw_data=record,
                )
            )

        for record in payload["app_role_assignments.json"]:
            db.add(
                AppRoleAssignment(
                    import_run_id=import_run.id,
                    assignment_external_id=_text(_get(record, "id", "assignment_id")),
                    app_role_id=_text(_get(record, "appRoleId", "app_role_id")),
                    created_datetime=_datetime(
                        _get(record, "createdDateTime", "created_datetime")
                    ),
                    principal_id=_text(_get(record, "principalId", "principal_id")),
                    principal_type=_text(
                        _get(record, "principalType", "principal_type")
                    ),
                    principal_display_name=_text(
                        _get(
                            record,
                            "principalDisplayName",
                            "principal_display_name",
                        )
                    ),
                    resource_id=_text(_get(record, "resourceId", "resource_id")),
                    resource_display_name=_text(
                        _get(
                            record,
                            "resourceDisplayName",
                            "resource_display_name",
                        )
                    ),
                    raw_data=record,
                )
            )

        for record in payload["directory_audits.json"]:
            initiated_by_type, initiated_by_id, initiated_by_display_name = _audit_initiator(
                record
            )

            db.add(
                DirectoryAuditEvent(
                    import_run_id=import_run.id,
                    audit_external_id=_text(_get(record, "id", "audit_id")),
                    activity_datetime=_datetime(
                        _get(record, "activityDateTime", "activity_datetime")
                    ),
                    activity_display_name=_text(
                        _get(
                            record,
                            "activityDisplayName",
                            "activity_display_name",
                        )
                    ),
                    category=_text(_get(record, "category")),
                    result=_text(_get(record, "result")),
                    correlation_id=_text(
                        _get(record, "correlationId", "correlation_id")
                    ),
                    initiated_by_type=initiated_by_type,
                    initiated_by_id=initiated_by_id,
                    initiated_by_display_name=initiated_by_display_name,
                    target_resources=_list(
                        _get(record, "targetResources", "target_resources")
                    ),
                    additional_details=_list(
                        _get(record, "additionalDetails", "additional_details")
                    ),
                    raw_data=record,
                )
            )

        for record in payload["sign_ins.json"]:
            db.add(
                SignInEvent(
                    import_run_id=import_run.id,
                    sign_in_external_id=_text(_get(record, "id", "sign_in_id")),
                    created_datetime=_datetime(
                        _get(record, "createdDateTime", "created_datetime")
                    ),
                    app_id=_text(_get(record, "appId", "app_id")),
                    app_display_name=_text(
                        _get(record, "appDisplayName", "app_display_name")
                    ),
                    service_principal_id=_text(
                        _get(record, "servicePrincipalId", "service_principal_id")
                    ),
                    service_principal_name=_text(
                        _get(
                            record,
                            "servicePrincipalName",
                            "service_principal_name",
                        )
                    ),
                    user_id=_text(_get(record, "userId", "user_id")),
                    user_principal_name=_text(
                        _get(record, "userPrincipalName", "user_principal_name")
                    ),
                    user_display_name=_text(
                        _get(record, "userDisplayName", "user_display_name")
                    ),
                    ip_address=_text(_get(record, "ipAddress", "ip_address")),
                    correlation_id=_text(
                        _get(record, "correlationId", "correlation_id")
                    ),
                    conditional_access_status=_text(
                        _get(
                            record,
                            "conditionalAccessStatus",
                            "conditional_access_status",
                        )
                    ),
                    risk_level=_text(
                        _get(
                            record,
                            "riskLevelAggregated",
                            "risk_level",
                        )
                    ),
                    resource_display_name=_text(
                        _get(
                            record,
                            "resourceDisplayName",
                            "resource_display_name",
                        )
                    ),
                    status_detail=_dict(_get(record, "status")),
                    location_detail=_dict(_get(record, "location")),
                    device_detail=_dict(_get(record, "deviceDetail", "device_detail")),
                    raw_data=record,
                )
            )

        import_run.status = "completed"
        import_run.completed_at = datetime.now(timezone.utc)
        import_run.evidence_summary = {
            "bundle_name": _text(manifest.get("bundle_name")),
            "generated_at": _text(manifest.get("generated_at")),
            "record_counts": record_counts,
        }

        db.commit()
        db.refresh(import_run)

        return import_run

    except Exception:
        db.rollback()
        raise


def _count_records(db: Session, model: Any, import_run_id: Any) -> int:
    statement = (
        select(func.count(model.id))
        .where(model.import_run_id == import_run_id)
    )

    return int(db.scalar(statement) or 0)


def build_import_summary(db: Session, import_run: ImportRun) -> dict[str, Any]:
    counts = {
        "applications": _count_records(db, Application, import_run.id),
        "service_principals": _count_records(db, ServicePrincipal, import_run.id),
        "owners": _count_records(db, Ownership, import_run.id),
        "credentials": _count_records(db, Credential, import_run.id),
        "oauth_permission_grants": _count_records(
            db,
            OAuthPermissionGrant,
            import_run.id,
        ),
        "app_role_assignments": _count_records(
            db,
            AppRoleAssignment,
            import_run.id,
        ),
        "directory_audits": _count_records(
            db,
            DirectoryAuditEvent,
            import_run.id,
        ),
        "sign_ins": _count_records(db, SignInEvent, import_run.id),
    }

    return {
        "import_run": serialize_import_run(import_run),
        "normalized_record_counts": counts,
    }