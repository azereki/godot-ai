"""Fail-closed contracts for signing and not-yet-authorized publication."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def test_signing_secret_check_uses_the_protected_environment() -> None:
    workflow = (WORKFLOWS / "verify-signing.yml").read_text(encoding="utf-8")
    assert "RELEASE_SIGNING_KEY_PEM" in workflow
    assert "environment: release-signing" in workflow


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


def test_signing_key_transfer_is_opt_in_protected_and_after_verification() -> None:
    raw = (WORKFLOWS / "verify-signing.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)
    dispatch = workflow.get(True, workflow.get("on"))["workflow_dispatch"]
    assert dispatch["inputs"]["copy_key_to_environment"]["default"] is False
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["verify"]
    assert job["environment"] == "release-signing"
    verify, copy = job["steps"][-2:]
    assert "openssl dgst -sha256 -verify" in verify["run"]
    assert "inputs.copy_key_to_environment" in copy["if"]
    assert "github.repository == 'hi-godot/godot-ai'" in copy["if"]
    assert "always()" not in copy["if"]
    assert copy["env"]["GH_TOKEN"] == "${{ secrets.RELEASE_KEY_MIGRATION_TOKEN }}"
    assert "upload-artifact" not in raw
    assert "gh secret delete" not in raw


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="POSIX shell step")
@pytest.mark.parametrize(
    "case", ["success", "missing_token", "missing_key", "exists", "list_error"]
)
def test_signing_key_transfer_shell_never_prints_or_overwrites_secrets(tmp_path: Path, case: str):
    workflow = yaml.safe_load((WORKFLOWS / "verify-signing.yml").read_text(encoding="utf-8"))
    step = workflow["jobs"]["verify"]["steps"][-1]["run"]
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        "#!/bin/bash\n"
        'if [ "$1 $2" = "secret list" ]; then\n'
        '  [ "$CASE" != "list_error" ] || exit 7\n'
        '  if [ "$CASE" = "exists" ]; then echo 1; else echo 0; fi\n'
        'elif [ "$1 $2" = "secret set" ]; then\n'
        '  printf "%s\\n" "$@" > "$ARGS_PATH"\n'
        '  cat > "$CAPTURE_PATH"\n'
        "else exit 8; fi\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o700)
    capture, arguments = tmp_path / "stdin", tmp_path / "arguments"
    secret, token = "synthetic-private-key\nnot-a-real-key", "synthetic-token"
    result = subprocess.run(
        ["bash", "-c", step],
        capture_output=True,
        text=True,
        timeout=10,
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
            "CASE": case,
            "CAPTURE_PATH": str(capture),
            "ARGS_PATH": str(arguments),
            "RELEASE_SIGNING_KEY_PEM": "" if case == "missing_key" else secret,
            "GH_TOKEN": "" if case == "missing_token" else token,
        },
    )
    assert secret not in result.stdout + result.stderr
    assert token not in result.stdout + result.stderr
    if case == "success":
        assert result.returncode == 0
        assert capture.read_text(encoding="utf-8") == secret
        assert arguments.read_text(encoding="utf-8").splitlines() == [
            "secret",
            "set",
            "RELEASE_SIGNING_KEY_PEM",
            "--repo",
            "hi-godot/godot-ai",
            "--env",
            "release-signing",
        ]
    else:
        assert result.returncode != 0
        assert not capture.exists()
        assert not arguments.exists()
