"""Tests for the local interactive self-update smoke harness."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "script" / "local-self-update-smoke"


def load_smoke_script() -> ModuleType:
    loader = SourceFileLoader("local_self_update_smoke", str(SCRIPT))
    module = ModuleType(loader.name)
    module.__file__ = str(SCRIPT)
    loader.exec_module(module)
    return module


def test_self_update_smoke_harness_prepares_fixture(tmp_path: Path) -> None:
    project = tmp_path / "self-update-smoke"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--no-launch",
            "--project-dir",
            str(project),
            "--base-version",
            "2.2.0",
            "--next-version",
            "2.2.1-self-update-smoke",
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )

    assert "Self-update smoke fixture ready" in result.stdout
    assert "click Update" in result.stdout
    assert "a new Godot*.ips" in result.stdout
    assert "/godot-ai/status" in result.stdout

    base_cfg = (project / "addons" / "godot_ai" / "plugin.cfg").read_text(encoding="utf-8")
    assert 'version="2.2.0"' in base_cfg

    # The smoke patches land on the manager file; the dock keeps only
    # the visible banner UI.
    base_manager = (project / "addons" / "godot_ai" / "utils" / "update_manager.gd").read_text(
        encoding="utf-8"
    )
    assert 'const SELF_UPDATE_SMOKE_DOWNLOAD_URL := "smoke://local-prestaged"' in base_manager
    assert (
        'const SELF_UPDATE_SMOKE_ZIP := "res://self_update_smoke/godot-ai-plugin-vnext.zip"'
        in base_manager
    )
    assert "FileAccess.get_file_as_bytes(src)" in base_manager
    assert "user-update-path.txt" in base_manager
    # `patch_local_update_banner` replaces `start_install()` by source range.
    # Keep update-manager state outside that range so train additions are not
    # silently stripped from the fixture and only discovered as parse errors
    # in the interactive smoke.
    assert "var _prewarm_pid := -1" in base_manager
    assert "const PREWARM_WAIT_BUDGET_MS := 180 * 1000" in base_manager

    base_configurator = (project / "addons" / "godot_ai" / "client_configurator.gd").read_text(
        encoding="utf-8"
    )
    assert "const DEFAULT_HTTP_PORT := 18000" in base_configurator
    assert "const DEFAULT_WS_PORT := 19500" in base_configurator
    assert 'const SELF_UPDATE_SMOKE_SERVER_VERSION := "2.2.0"' in base_configurator
    assert "var version := SELF_UPDATE_SMOKE_SERVER_VERSION" in base_configurator
    assert "return default_port" in base_configurator
    assert "static func ensure_settings_registered() -> void:" in base_configurator
    assert "static func _register_port_setting(" in base_configurator

    base_settings = (project / "addons" / "godot_ai" / "utils" / "settings.gd").read_text(
        encoding="utf-8"
    )
    assert "godot_ai_self_update_smoke/excluded_domains" in base_settings

    base_plugin = (project / "addons" / "godot_ai" / "plugin.gd").read_text(encoding="utf-8")
    assert "godot_ai_self_update_smoke/managed_server_pid" in base_plugin

    base_lifecycle = (project / "addons" / "godot_ai" / "utils" / "server_lifecycle.gd").read_text(
        encoding="utf-8"
    )
    assert 'const SELF_UPDATE_SMOKE_EXPECTED_SERVER_VERSION := "2.2.0"' in base_lifecycle
    assert "func _expected_server_version() -> String:" in base_lifecycle
    assert "return SELF_UPDATE_SMOKE_EXPECTED_SERVER_VERSION" in base_lifecycle

    zip_path = project / "self_update_smoke" / "godot-ai-plugin-vnext.zip"
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "addons/godot_ai/plugin.cfg" in names
        assert "addons/godot_ai/mcp_dock.gd" in names
        assert "addons/godot_ai/utils/update_manager.gd" in names
        assert "addons/godot_ai/utils/self_update_smoke_base.gd" in names
        assert "addons/godot_ai/utils/self_update_smoke_child.gd" in names
        vnext_cfg = zf.read("addons/godot_ai/plugin.cfg").decode()
        vnext_dock = zf.read("addons/godot_ai/mcp_dock.gd").decode()
        vnext_manager = zf.read("addons/godot_ai/utils/update_manager.gd").decode()
        vnext_configurator = zf.read("addons/godot_ai/client_configurator.gd").decode()
        vnext_settings = zf.read("addons/godot_ai/utils/settings.gd").decode()
        vnext_plugin = zf.read("addons/godot_ai/plugin.gd").decode()
        vnext_lifecycle = zf.read("addons/godot_ai/utils/server_lifecycle.gd").decode()
        vnext_base = zf.read("addons/godot_ai/utils/self_update_smoke_base.gd").decode()
        vnext_child = zf.read("addons/godot_ai/utils/self_update_smoke_child.gd").decode()

    assert 'version="2.2.1-self-update-smoke"' in vnext_cfg
    # The smoke download URL is no longer in the dock (it lives on the
    # manager); the dock should not contain it either.
    assert "smoke://local-prestaged" not in vnext_dock
    assert "smoke://local-prestaged" not in vnext_manager
    assert "var _prewarm_pid := -1" in vnext_manager
    assert "const PREWARM_WAIT_BUDGET_MS := 180 * 1000" in vnext_manager
    assert 'var _self_update_smoke_trigger: Dictionary = {"armed": true}' in vnext_dock
    assert 'var _self_update_smoke_array_trigger: Array[String] = ["armed"]' in vnext_dock
    assert "MCP | [self-update-smoke vnext _exit_tree]" in vnext_dock
    assert "SelfUpdateSmokeChild" in vnext_dock
    assert "class_name McpSelfUpdateSmokeBase" in vnext_base
    assert "class_name McpSelfUpdateSmokeChild" in vnext_child
    assert "extends McpSelfUpdateSmokeBase" in vnext_child
    assert "const DEFAULT_HTTP_PORT := 18000" in vnext_configurator
    assert 'const SELF_UPDATE_SMOKE_SERVER_VERSION := "2.2.0"' in vnext_configurator
    # uvx pin: stock releases format with `version`; local builds go through
    # `_pypi_pin_version` and format with `pypi_version`.
    assert (
        'godot-ai==%s" % version' in vnext_configurator
        or 'godot-ai==%s" % pypi_version' in vnext_configurator
    )
    assert "var version := SELF_UPDATE_SMOKE_SERVER_VERSION" in vnext_configurator
    assert "return default_port" in vnext_configurator
    assert "static func ensure_settings_registered() -> void:" in vnext_configurator
    assert "static func _register_port_setting(" in vnext_configurator
    assert "godot_ai_self_update_smoke/excluded_domains" in vnext_settings
    assert "godot_ai_self_update_smoke/managed_server_pid" in vnext_plugin
    assert 'const SELF_UPDATE_SMOKE_EXPECTED_SERVER_VERSION := "2.2.0"' in vnext_lifecycle
    assert "func _expected_server_version() -> String:" in vnext_lifecycle
    assert "return SELF_UPDATE_SMOKE_EXPECTED_SERVER_VERSION" in vnext_lifecycle


def test_self_update_smoke_log_verifier_rejects_external_adoption() -> None:
    smoke = load_smoke_script()
    lines = [
        "MCP | foreign server already running on port 18000, using existing",
        "MCP | self-update smoke: staged local zip /tmp/update.zip",
        "MCP | stopped server (PID [123])",
        "MCP | update runner enabling new plugin",
    ]

    assert smoke.smoke_adopted_existing_server_before_update(lines)
    assert not smoke.smoke_started_own_server_before_update(lines)
    assert smoke.smoke_stopped_server_during_update(lines)


def test_self_update_smoke_log_verifier_requires_managed_stop_after_staging() -> None:
    smoke = load_smoke_script()
    lines = [
        "MCP | started server (PID 123, v2.2.1): godot-ai",
        "MCP | self-update smoke: staged local zip /tmp/update.zip",
        "MCP | update runner enabling new plugin",
    ]

    assert smoke.smoke_started_own_server_before_update(lines)
    assert not smoke.smoke_adopted_existing_server_before_update(lines)
    assert not smoke.smoke_stopped_server_during_update(lines)


def test_self_update_smoke_log_verifier_rejects_version_mismatch() -> None:
    smoke = load_smoke_script()
    lines = [
        "MCP | started server (PID 123, v2.2.0): godot-ai",
        "MCP | self-update smoke: staged local zip /tmp/update.zip",
        "MCP | stopped server (PID [123])",
        "MCP | update runner enabling new plugin",
        "MCP | plugin loaded",
        (
            "MCP | Port 18000 is occupied by godot-ai server v2.2.0; "
            "plugin expects v2.2.1. Stop the old server or change both HTTP and WS ports."
        ),
    ]

    assert smoke.smoke_reported_server_version_mismatch(lines)


def test_self_update_smoke_log_verifier_accepts_matching_versions() -> None:
    smoke = load_smoke_script()
    lines = [
        "MCP | started server (PID 123, v2.2.0): godot-ai",
        "MCP | self-update smoke: staged local zip /tmp/update.zip",
        "MCP | stopped server (PID [123])",
        "MCP | update runner enabling new plugin",
        "MCP | started server (PID 456, v2.2.0): godot-ai",
        "MCP | plugin loaded",
    ]

    assert not smoke.smoke_reported_server_version_mismatch(lines)


def test_self_update_smoke_harness_refuses_unmarked_existing_dir(tmp_path: Path) -> None:
    project = tmp_path / "existing-project"
    project.mkdir()
    (project / "project.godot").write_text("not generated by the harness\n")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--no-launch",
            "--project-dir",
            str(project),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "not marked as a smoke fixture" in result.stderr


def _make_addon_with(tmp_path: Path, *, present: tuple[str, ...]) -> Path:
    addon = tmp_path / "addon"
    (addon / "utils").mkdir(parents=True)
    for rel in present:
        (addon / rel).write_text("# fixture stub\n", encoding="utf-8")
    return addon


def test_v240_preflight_passes_when_both_files_present(tmp_path: Path) -> None:
    smoke = load_smoke_script()
    addon = _make_addon_with(
        tmp_path,
        present=("utils/server_lifecycle.gd", "utils/update_manager.gd"),
    )
    # Validator returns None on success and raises HarnessError otherwise; the
    # assertion both documents intent and trips the runner's zero-assertion guard.
    assert smoke._require_v240_plus_addon_shape(addon, "2.4.0") is None


@pytest.mark.parametrize(
    ("present", "expected_missing"),
    [
        (("utils/update_manager.gd",), "utils/server_lifecycle.gd"),
        (("utils/server_lifecycle.gd",), "utils/update_manager.gd"),
    ],
)
def test_v240_preflight_raises_clear_harness_error_for_single_missing_file(
    tmp_path: Path, present: tuple[str, ...], expected_missing: str
) -> None:
    smoke = load_smoke_script()
    addon = _make_addon_with(tmp_path, present=present)
    with pytest.raises(smoke.HarnessError) as exc_info:
        smoke._require_v240_plus_addon_shape(addon, "2.3.2")
    message = str(exc_info.value)
    assert expected_missing in message, message
    assert "2.3.2" in message, message
    assert "v2.4.0" in message, message
    assert "--base-from-release-tag" in message, message


def test_v240_preflight_lists_all_missing_files_when_both_absent(tmp_path: Path) -> None:
    smoke = load_smoke_script()
    addon = _make_addon_with(tmp_path, present=())
    with pytest.raises(smoke.HarnessError) as exc_info:
        smoke._require_v240_plus_addon_shape(addon, "2.3.2")
    message = str(exc_info.value)
    assert "utils/server_lifecycle.gd" in message, message
    assert "utils/update_manager.gd" in message, message


def test_self_update_smoke_harness_refuses_suspicious_marker(tmp_path: Path) -> None:
    project = tmp_path / "existing-project"
    (project / ".godot-ai-self-update-smoke").mkdir(parents=True)
    (project / ".godot-ai-self-update-smoke" / "marker.txt").write_text("marker\n")
    (project / "project.godot").write_text("not generated by the harness\n")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--no-launch",
            "--project-dir",
            str(project),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "has a smoke marker but does not look generated" in result.stderr


def test_smoke_new_plugin_loaded_after_update_requires_both_markers() -> None:
    smoke = load_smoke_script()
    before_reload = [
        "MCP | started server (PID 123, v2.2.0): godot-ai",
        "MCP | self-update smoke: staged local zip /tmp/update.zip",
        "MCP | stopped server (PID [123])",
        "MCP | update runner enabling new plugin",
    ]
    assert not smoke.smoke_new_plugin_loaded_after_update(before_reload)
    after_reload = before_reload + ["MCP | plugin loaded"]
    assert smoke.smoke_new_plugin_loaded_after_update(after_reload)


def test_status_reports_live_version_requires_name_and_pin() -> None:
    smoke = load_smoke_script()
    assert not smoke.status_reports_live_version(None, "3.2.4")
    assert not smoke.status_reports_live_version(
        {"name": "other", "server_version": "3.2.4"}, "3.2.4"
    )
    assert not smoke.status_reports_live_version(
        {"name": "godot-ai", "server_version": "3.2.3"}, "3.2.4"
    )
    assert smoke.status_reports_live_version(
        {"name": "godot-ai", "server_version": "3.2.4"}, "3.2.4"
    )


class _StatusHandler(BaseHTTPRequestHandler):
    payload: dict[str, Any] = {"name": "godot-ai", "server_version": "3.2.4"}

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/godot-ai/status":
            self.send_error(404)
            return
        body = json.dumps(self.payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def test_fetch_and_wait_for_live_status() -> None:
    smoke = load_smoke_script()
    _StatusHandler.payload = {"name": "godot-ai", "server_version": "3.2.4"}
    server = HTTPServer(("127.0.0.1", 0), _StatusHandler)
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = smoke.fetch_status_payload(port)
        assert payload == {"name": "godot-ai", "server_version": "3.2.4"}
        live = smoke.wait_for_live_status(port, "3.2.4", timeout=2.0, poll=0.05)
        assert live == payload
        missing = smoke.wait_for_live_status(port, "9.9.9", timeout=0.2, poll=0.05)
        assert missing == payload
        assert not smoke.status_reports_live_version(missing, "9.9.9")
    finally:
        server.shutdown()
        server.server_close()


def test_fetch_status_payload_none_when_port_dark() -> None:
    smoke = load_smoke_script()
    assert smoke.fetch_status_payload(1, timeout=0.2) is None


class _TruncatedStatusHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = b'{"name":"godot-ai","server_version":"3.2.4"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body) + 64))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def test_fetch_status_payload_none_on_truncated_body() -> None:
    smoke = load_smoke_script()
    server = HTTPServer(("127.0.0.1", 0), _TruncatedStatusHandler)
    port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert smoke.fetch_status_payload(port, timeout=1.0) is None
    finally:
        server.shutdown()
        server.server_close()


def _minimal_smoke_project(tmp_path: Path, version: str) -> Path:
    project = tmp_path / "smoke"
    addon = project / "addons" / "godot_ai"
    addon.mkdir(parents=True)
    (addon / "plugin.cfg").write_text(f'version="{version}"\n', encoding="utf-8")
    marker = project / ".godot-ai-self-update-smoke"
    marker.mkdir()
    consumed = tmp_path / "consumed-update-dir"
    (marker / "user-update-path.txt").write_text(str(consumed), encoding="utf-8")
    return project


def test_verify_post_run_requires_live_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    smoke = load_smoke_script()
    project = _minimal_smoke_project(tmp_path, "2.2.1-self-update-smoke")
    lines = [
        "MCP | started server (PID 123, v2.2.0): godot-ai",
        "MCP | self-update smoke: staged local zip /tmp/update.zip",
        "MCP | stopped server (PID [123])",
        "MCP | update runner enabling new plugin",
        "MCP | plugin loaded",
    ]
    ok = smoke.verify_post_run(
        project,
        "2.2.1-self-update-smoke",
        set(),
        time.time(),
        lines,
        post_update_status=None,
        next_server_version="2.2.0",
    )
    captured = capsys.readouterr().out
    assert ok is False
    assert "post-update /godot-ai/status was not live" in captured


def test_verify_post_run_accepts_live_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    smoke = load_smoke_script()
    project = _minimal_smoke_project(tmp_path, "2.2.1-self-update-smoke")
    lines = [
        "MCP | started server (PID 123, v2.2.0): godot-ai",
        "MCP | self-update smoke: staged local zip /tmp/update.zip",
        "MCP | stopped server (PID [123])",
        "MCP | update runner enabling new plugin",
        "MCP | plugin loaded",
    ]
    ok = smoke.verify_post_run(
        project,
        "2.2.1-self-update-smoke",
        set(),
        time.time(),
        lines,
        post_update_status={"name": "godot-ai", "server_version": "2.2.0"},
        next_server_version="2.2.0",
    )
    captured = capsys.readouterr().out
    assert ok is True
    assert "PASS: post-update /godot-ai/status live v2.2.0" in captured
