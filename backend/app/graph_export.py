from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx


REQUIRED_BUNDLE_FILES = [
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


class GraphExportError(RuntimeError):
    pass


@dataclass(frozen=True)
class GraphExportConfig:
    tenant_id: str | None
    tenant_display_name: str | None
    client_id: str | None
    client_secret: str | None
    graph_base_url: str
    authority_base_url: str

    @classmethod
    def from_environment(cls) -> "GraphExportConfig":
        return cls(
            tenant_id=os.getenv("GRANTSCOPE_GRAPH_TENANT_ID"),
            tenant_display_name=os.getenv(
                "GRANTSCOPE_GRAPH_TENANT_DISPLAY_NAME"
            ),
            client_id=os.getenv("GRANTSCOPE_GRAPH_CLIENT_ID"),
            client_secret=os.getenv("GRANTSCOPE_GRAPH_CLIENT_SECRET"),
            graph_base_url=os.getenv(
                "GRANTSCOPE_GRAPH_BASE_URL",
                "https://graph.microsoft.com",
            ).rstrip("/"),
            authority_base_url=os.getenv(
                "GRANTSCOPE_GRAPH_AUTHORITY_BASE_URL",
                "https://login.microsoftonline.com",
            ).rstrip("/"),
        )

    def missing_fields(self) -> list[str]:
        required = {
            "GRANTSCOPE_GRAPH_TENANT_ID": self.tenant_id,
            "GRANTSCOPE_GRAPH_CLIENT_ID": self.client_id,
            "GRANTSCOPE_GRAPH_CLIENT_SECRET": self.client_secret,
        }

        return [
            name
            for name, value in required.items()
            if not value or not value.strip()
        ]

    def is_configured(self) -> bool:
        return not self.missing_fields()


class GraphClient:
    def __init__(self, config: GraphExportConfig) -> None:
        self.config = config
        self.http = httpx.Client(
            timeout=httpx.Timeout(45.0, connect=20.0),
            follow_redirects=False,
        )
        self._access_token: str | None = None

    def close(self) -> None:
        self.http.close()

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        if not self.config.is_configured():
            raise GraphExportError(
                "Graph connector configuration is incomplete."
            )

        token_url = (
            f"{self.config.authority_base_url}/"
            f"{self.config.tenant_id}/oauth2/v2.0/token"
        )

        response = self.http.post(
            token_url,
            data={
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
        )

        if response.status_code >= 400:
            raise GraphExportError(
                "Unable to obtain a Microsoft Graph access token. "
                f"HTTP {response.status_code}: {response.text[:500]}"
            )

        payload = response.json()
        token = payload.get("access_token")

        if not token:
            raise GraphExportError(
                "Microsoft identity platform response did not contain "
                "an access token."
            )

        self._access_token = token
        return token

    def _get_json(
        self,
        url: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        token = self._get_access_token()

        response = self.http.get(
            url,
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "5")

            try:
                wait_seconds = min(int(retry_after), 30)
            except ValueError:
                wait_seconds = 5

            time.sleep(wait_seconds)

            response = self.http.get(
                url,
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )

        if response.status_code >= 400:
            raise GraphExportError(
                f"Microsoft Graph request failed. HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        payload = response.json()

        if not isinstance(payload, dict):
            raise GraphExportError(
                "Microsoft Graph returned an unexpected response format."
            )

        return payload

    def list_collection(
        self,
        path: str,
        *,
        version: str = "v1.0",
        params: dict[str, str] | None = None,
        max_items: int = 100,
    ) -> list[dict[str, Any]]:
        url = f"{self.config.graph_base_url}/{version}/{path.lstrip('/')}"
        next_params = params
        records: list[dict[str, Any]] = []

        while url and len(records) < max_items:
            payload = self._get_json(url, next_params)
            values = payload.get("value", [])

            if not isinstance(values, list):
                raise GraphExportError(
                    f"Microsoft Graph collection {path} did not return a value array."
                )

            remaining = max_items - len(records)

            for value in values[:remaining]:
                if isinstance(value, dict):
                    records.append(value)

            next_url = payload.get("@odata.nextLink")
            url = next_url if isinstance(next_url, str) else ""
            next_params = None

        return records


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")


def object_owner_records(
    resource_type: str,
    resource_id: str,
    owners: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for owner in owners:
        owner_id = owner.get("id")

        if not owner_id:
            continue

        object_type = str(owner.get("@odata.type", "directoryObject"))
        normalized_type = object_type.split(".")[-1]

        account_enabled = owner.get("accountEnabled")

        if not isinstance(account_enabled, bool):
            account_enabled = None

        records.append(
            {
                "resource_type": resource_type,
                "resource_id": resource_id,
                "owner_id": owner_id,
                "owner_type": normalized_type,
                "owner_display_name": owner.get("displayName"),
                "owner_user_principal_name": owner.get("userPrincipalName"),
                "owner_account_enabled": account_enabled,
            }
        )

    return records


def credential_records(
    objects: list[dict[str, Any]],
    resource_type: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for directory_object in objects:
        resource_id = directory_object.get("id")

        if not resource_id:
            continue

        for credential_type, field_name in (
            ("password", "passwordCredentials"),
            ("certificate", "keyCredentials"),
        ):
            credentials = directory_object.get(field_name, [])

            if not isinstance(credentials, list):
                continue

            for index, credential in enumerate(credentials):
                if not isinstance(credential, dict):
                    continue

                key_id = credential.get("keyId")
                external_id = (
                    f"{resource_id}:{credential_type}:"
                    f"{key_id or index}"
                )

                records.append(
                    {
                        "id": external_id,
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "credential_type": credential_type,
                        "displayName": credential.get("displayName"),
                        "keyId": key_id,
                        "startDateTime": credential.get("startDateTime"),
                        "endDateTime": credential.get("endDateTime"),
                        "created_from_audit_event_id": None,
                    }
                )

    return records


def enrich_app_role_assignments(
    assignments: list[dict[str, Any]],
    service_principals_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []

    for assignment in assignments:
        enriched_assignment = dict(assignment)
        resource_id = assignment.get("resourceId")
        app_role_id = assignment.get("appRoleId")

        resource_service_principal = service_principals_by_id.get(
            str(resource_id)
        )

        if resource_service_principal:
            app_roles = resource_service_principal.get("appRoles", [])

            for app_role in app_roles:
                if (
                    isinstance(app_role, dict)
                    and app_role.get("id") == app_role_id
                ):
                    enriched_assignment["appRoleValue"] = app_role.get(
                        "value"
                    )
                    break

        enriched.append(enriched_assignment)

    return enriched


def create_bundle_bytes(payload: dict[str, Any]) -> bytes:
    missing = [
        file_name
        for file_name in REQUIRED_BUNDLE_FILES
        if file_name not in payload
    ]

    if missing:
        raise GraphExportError(
            "Bundle payload is missing required files: "
            + ", ".join(missing)
        )

    archive_buffer = io.BytesIO()

    with zipfile.ZipFile(
        archive_buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for file_name in REQUIRED_BUNDLE_FILES:
            archive.writestr(
                file_name,
                json.dumps(payload[file_name], indent=2) + "\n",
            )

    return archive_buffer.getvalue()


def safe_collection(
    coverage: dict[str, Any],
    label: str,
    callback: Any,
) -> list[dict[str, Any]]:
    try:
        values = callback()
        coverage["collected"][label] = len(values)
        return values
    except GraphExportError as error:
        coverage["collected"][label] = 0
        coverage["warnings"].append(
            {
                "source": label,
                "message": str(error),
            }
        )
        return []


def collect_graph_bundle(
    config: GraphExportConfig,
    *,
    lookback_days: int,
    max_objects: int,
    include_beta_service_principal_signins: bool,
) -> tuple[bytes, dict[str, Any]]:
    if not config.is_configured():
        raise GraphExportError(
            "Missing Graph connector configuration: "
            + ", ".join(config.missing_fields())
        )

    if lookback_days < 1 or lookback_days > 90:
        raise GraphExportError(
            "lookback_days must be between 1 and 90."
        )

    if max_objects < 1 or max_objects > 1000:
        raise GraphExportError(
            "max_objects must be between 1 and 1000."
        )

    started_at = datetime.now(timezone.utc)
    start_time = started_at - timedelta(days=lookback_days)
    start_filter = iso_utc(start_time)

    coverage: dict[str, Any] = {
        "collection_mode": "read_only_graph_export",
        "lookback_days": lookback_days,
        "service_principal_signins_beta_enabled": (
            include_beta_service_principal_signins
        ),
        "collected": {},
        "warnings": [],
    }

    client = GraphClient(config)

    try:
        applications = client.list_collection(
            "applications",
            params={
                "$select": (
                    "id,appId,displayName,createdDateTime,signInAudience,"
                    "publisherDomain,verifiedPublisher,"
                    "disabledByMicrosoftStatus,passwordCredentials,"
                    "keyCredentials"
                ),
                "$top": "100",
            },
            max_items=max_objects,
        )

        coverage["collected"]["applications"] = len(applications)

        service_principals = client.list_collection(
            "servicePrincipals",
            params={
                "$select": (
                    "id,appId,displayName,servicePrincipalType,"
                    "accountEnabled,appOwnerOrganizationId,publisherName,"
                    "verifiedPublisher,tags,passwordCredentials,"
                    "keyCredentials,appRoles"
                ),
                "$top": "100",
            },
            max_items=max_objects,
        )

        coverage["collected"]["service_principals"] = len(
            service_principals
        )

        service_principals_by_id = {
            str(item["id"]): item
            for item in service_principals
            if item.get("id")
        }

        application_owners: list[dict[str, Any]] = []

        for application in applications:
            application_id = application.get("id")

            if not application_id:
                continue

            owners = safe_collection(
                coverage,
                "application_owner_queries",
                lambda app_id=application_id: client.list_collection(
                    f"applications/{app_id}/owners",
                    params={
                        "$select": (
                            "id,displayName,userPrincipalName,"
                            "accountEnabled"
                        )
                    },
                    max_items=100,
                ),
            )

            application_owners.extend(
                object_owner_records(
                    "application",
                    str(application_id),
                    owners,
                )
            )

        service_principal_owners: list[dict[str, Any]] = []

        for service_principal in service_principals:
            service_principal_id = service_principal.get("id")

            if not service_principal_id:
                continue

            owners = safe_collection(
                coverage,
                "service_principal_owner_queries",
                lambda sp_id=service_principal_id: client.list_collection(
                    f"servicePrincipals/{sp_id}/owners",
                    params={
                        "$select": (
                            "id,displayName,userPrincipalName,"
                            "accountEnabled"
                        )
                    },
                    max_items=100,
                ),
            )

            service_principal_owners.extend(
                object_owner_records(
                    "servicePrincipal",
                    str(service_principal_id),
                    owners,
                )
            )

        permission_grants = client.list_collection(
            "oauth2PermissionGrants",
            params={"$top": "100"},
            max_items=max_objects,
        )

        coverage["collected"]["oauth2_permission_grants"] = len(
            permission_grants
        )

        all_assignments: list[dict[str, Any]] = []

        for service_principal in service_principals:
            service_principal_id = service_principal.get("id")

            if not service_principal_id:
                continue

            assignments = safe_collection(
                coverage,
                "app_role_assignment_queries",
                lambda sp_id=service_principal_id: client.list_collection(
                    f"servicePrincipals/{sp_id}/appRoleAssignments",
                    params={"$top": "100"},
                    max_items=100,
                ),
            )

            all_assignments.extend(assignments)

        app_role_assignments = enrich_app_role_assignments(
            all_assignments,
            service_principals_by_id,
        )

        coverage["collected"]["app_role_assignments"] = len(
            app_role_assignments
        )

        directory_audits = safe_collection(
            coverage,
            "directory_audits",
            lambda: client.list_collection(
                "auditLogs/directoryAudits",
                params={
                    "$filter": f"activityDateTime ge {start_filter}",
                    "$top": "100",
                },
                max_items=max_objects,
            ),
        )

        sign_ins = safe_collection(
            coverage,
            "sign_ins_v1",
            lambda: client.list_collection(
                "auditLogs/signIns",
                params={
                    "$filter": f"createdDateTime ge {start_filter}",
                    "$top": "100",
                },
                max_items=max_objects,
            ),
        )

        if include_beta_service_principal_signins:
            beta_sign_ins = safe_collection(
                coverage,
                "service_principal_sign_ins_beta",
                lambda: client.list_collection(
                    "auditLogs/signIns",
                    version="beta",
                    params={
                        "$filter": (
                            f"(createdDateTime ge {start_filter}) "
                            "and signInEventTypes/any(t: "
                            "t eq 'servicePrincipal')"
                        ),
                        "$top": "100",
                    },
                    max_items=max_objects,
                ),
            )

            existing_ids = {
                item.get("id")
                for item in sign_ins
                if item.get("id")
            }

            for sign_in in beta_sign_ins:
                if sign_in.get("id") not in existing_ids:
                    sign_ins.append(sign_in)

        credentials = (
            credential_records(applications, "application")
            + credential_records(
                service_principals,
                "servicePrincipal",
            )
        )

        coverage["collected"]["owners"] = (
            len(application_owners)
            + len(service_principal_owners)
        )
        coverage["collected"]["credentials"] = len(credentials)
        coverage["collected"]["sign_ins_total"] = len(sign_ins)

        payload = {
            "manifest.json": {
                "schema_version": "1.0",
                "bundle_name": (
                    "live-graph-export-"
                    f"{started_at.strftime('%Y%m%dT%H%M%SZ')}"
                ),
                "generated_at": iso_utc(started_at),
                "tenant": {
                    "tenant_id": config.tenant_id,
                    "display_name": (
                        config.tenant_display_name
                        or config.tenant_id
                    ),
                },
                "collection": coverage,
            },
            "applications.json": applications,
            "service_principals.json": service_principals,
            "owners.json": (
                application_owners
                + service_principal_owners
            ),
            "credentials.json": credentials,
            "oauth2_permission_grants.json": permission_grants,
            "app_role_assignments.json": app_role_assignments,
            "directory_audits.json": directory_audits,
            "sign_ins.json": sign_ins,
        }

        return create_bundle_bytes(payload), coverage

    finally:
        client.close()


def configuration_summary(config: GraphExportConfig) -> dict[str, Any]:
    return {
        "configured": config.is_configured(),
        "missing_fields": config.missing_fields(),
        "graph_base_url": config.graph_base_url,
        "tenant_display_name": config.tenant_display_name,
        "client_secret_present": bool(config.client_secret),
        "read_only": True,
        "beta_service_principal_signins_default": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect read-only Microsoft Graph evidence and create "
            "a GrantScope-compatible ZIP bundle."
        )
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Show connector configuration status without contacting Graph.",
    )

    parser.add_argument(
        "--lookback-days",
        type=int,
        default=30,
        help="Audit and sign-in collection period. Default: 30.",
    )

    parser.add_argument(
        "--max-objects",
        type=int,
        default=100,
        help="Maximum records per collection. Default: 100.",
    )

    parser.add_argument(
        "--include-beta-service-principal-signins",
        action="store_true",
        help=(
            "Opt in to the Microsoft Graph beta endpoint for "
            "service-principal sign-ins."
        ),
    )

    parser.add_argument(
        "--output-dir",
        default="/app/exports",
        help="Output directory inside the API container.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = GraphExportConfig.from_environment()

    if args.check:
        print(
            json.dumps(
                configuration_summary(config),
                indent=2,
            )
        )
        return 0

    bundle_bytes, coverage = collect_graph_bundle(
        config,
        lookback_days=args.lookback_days,
        max_objects=args.max_objects,
        include_beta_service_principal_signins=(
            args.include_beta_service_principal_signins
        ),
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    output_file = output_dir / f"grantscope-graph-export-{timestamp}.zip"
    output_file.write_bytes(bundle_bytes)

    print(
        json.dumps(
            {
                "status": "completed",
                "output_file": str(output_file),
                "bytes_written": output_file.stat().st_size,
                "coverage": coverage,
            },
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GraphExportError as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": str(error),
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)