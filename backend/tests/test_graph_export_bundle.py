from app.graph_export import create_bundle_bytes
from app.services.bundle_importer import read_bundle_from_zip


def test_graph_export_bundle_matches_grantscope_contract() -> None:
    payload = {
        "manifest.json": {
            "schema_version": "1.0",
            "bundle_name": "graph-export-test",
            "generated_at": "2026-07-03T20:00:00Z",
            "tenant": {
                "tenant_id": "33333333-3333-3333-3333-333333333333",
                "display_name": "Graph Export Test Tenant",
            },
        },
        "applications.json": [],
        "service_principals.json": [],
        "owners.json": [],
        "credentials.json": [],
        "oauth2_permission_grants.json": [],
        "app_role_assignments.json": [],
        "directory_audits.json": [],
        "sign_ins.json": [],
    }

    archive_bytes = create_bundle_bytes(payload)
    parsed = read_bundle_from_zip(archive_bytes)

    assert parsed["manifest.json"]["schema_version"] == "1.0"
    assert parsed["manifest.json"]["bundle_name"] == "graph-export-test"
    assert parsed["applications.json"] == []
    assert parsed["sign_ins.json"] == []