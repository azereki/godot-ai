"""Fail-closed contracts for signing and not-yet-authorized publication."""

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def test_signing_secret_check_uses_the_protected_environment() -> None:
    workflow = (WORKFLOWS / "verify-signing.yml").read_text(encoding="utf-8")
    assert "RELEASE_SIGNING_KEY_PEM" in workflow
    assert "environment: release-signing" in workflow
    assert yaml.safe_load(workflow)["permissions"] == {"contents": "read"}
    for retired in ("copy_key_to_environment", "RELEASE_KEY_MIGRATION_TOKEN", "gh secret"):
        assert retired not in workflow


def test_v4_publication_is_manual_and_fails_before_credentials_or_writes() -> None:
    path = WORKFLOWS / "release.yml"
    raw = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)

    triggers = workflow.get(True, workflow.get("on"))
    assert set(triggers) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"publication-gate"}
    assert "exit 1" in raw
    assert "immutable A/B qualification artifacts" in raw
    for forbidden in (
        "RELEASE_SIGNING_KEY_PEM",
        "gh release create",
        "action-gh-release",
        "gh-action-pypi-publish",
        "contents: write",
        "tags:",
    ):
        assert forbidden not in raw


def test_legacy_auto_bump_tag_push_and_dispatch_workflow_is_retired() -> None:
    assert not (WORKFLOWS / "bump-and-release.yml").exists()
