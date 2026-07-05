from pathlib import Path

from app.services.bundle_importer import REQUIRED_JSON_FILES, read_bundle_from_zip


def test_benign_demo_bundle_matches_contract() -> None:
    zip_path = Path("/app/sample-data/benign-collaboration-app.zip")
    payload = read_bundle_from_zip(zip_path.read_bytes())

    assert payload["manifest.json"]["schema_version"] == "1.0"
    assert payload["manifest.json"]["bundle_name"] == "benign-collaboration-app"

    for required_file in REQUIRED_JSON_FILES:
        assert required_file in payload

    assert len(payload["applications.json"]) == 1
    assert len(payload["service_principals.json"]) == 1
    assert len(payload["owners.json"]) == 2
    assert len(payload["credentials.json"]) == 1
    assert len(payload["oauth2_permission_grants.json"]) == 1
    assert len(payload["directory_audits.json"]) == 2
    assert len(payload["sign_ins.json"]) == 1