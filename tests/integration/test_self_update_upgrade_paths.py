from __future__ import annotations

import json
import shutil
from pathlib import Path

from godot_ai import __version__ as LIVE_SERVER_VERSION
from tests.integration._self_update_fixture import (
    LIVE_HTTP_PORT,
    LIVE_WS_PORT,
    PLUGIN_ROOT,
    POST_UPDATE_STATUS_FILE,
    ROOT,
    TEST_ZIP_NAME,
    assert_no_update_parse_errors,
    copy_addon_tree,
    create_plugin_zip,
    godot_bin_or_skip,
    link_dev_checkout_anchor,
    load_smoke_script,
    patch_fixture_addon,
    prepare_project_shell,
    read_plugin_version,
    run_godot_editor,
    write_forward_driver,
    write_install_update_driver,
)


def test_install_update_driver_calls_plugin_handoff(tmp_path: Path) -> None:
    project = tmp_path / "driver-only"
    project.mkdir()
    write_install_update_driver(project, http_port=LIVE_HTTP_PORT)
    text = (project / "_test_runner_driver.gd").read_text(encoding="utf-8")
    assert "plugin.install_downloaded_update(ZIP_PATH, TEMP_DIR, null)" in text
    assert f"const HTTP_PORT := {LIVE_HTTP_PORT}" in text
    assert "/godot-ai/status" in text
    assert "SELF_UPDATE_TEST | calling install_downloaded_update" in text


def test_current_runner_upgrades_to_synthetic_next_without_parse_errors(
    tmp_path: Path,
) -> None:
    """Forward regression for the fixed runner.

    This stages current source as the installed base, builds a synthetic next
    release that adds a new file referencing a new constant on an existing
    load-surface script, and drives the real runner's `start(...)` path.
    """

    godot_bin = godot_bin_or_skip()
    smoke = load_smoke_script()
    project = tmp_path / "self-update-forward"
    base_version = read_plugin_version(PLUGIN_ROOT / "plugin.cfg")
    next_version = smoke.bump_patch_version(base_version)
    server_version = base_version

    prepare_project_shell(project)
    write_forward_driver(project)

    base_addon = project / "addons" / "godot_ai"
    copy_addon_tree(PLUGIN_ROOT, base_addon)
    patch_fixture_addon(
        base_addon,
        version=base_version,
        server_version=server_version,
        next_version=next_version,
        skip_server_start=True,
    )

    vnext_addon = project / ".self-update-vnext" / "addons" / "godot_ai"
    copy_addon_tree(PLUGIN_ROOT, vnext_addon)
    patch_fixture_addon(
        vnext_addon,
        version=next_version,
        server_version=server_version,
        next_version=next_version,
        skip_server_start=True,
    )
    smoke.patch_vnext_hot_reload_trigger(vnext_addon / "mcp_dock.gd")
    patch_synthetic_next_shape(vnext_addon)

    zip_path = project / "_test_update_zip" / TEST_ZIP_NAME
    create_plugin_zip(vnext_addon, zip_path)

    log = run_godot_editor(project, godot_bin, allow_headless=True)

    assert_no_update_parse_errors(log)
    assert "SELF_UPDATE_TEST | synthetic handler marker synthetic_next" in log
    assert read_plugin_version(base_addon / "plugin.cfg") == next_version
    assert (base_addon / "handlers" / "self_update_synthetic_next.gd").is_file()

    shutil.rmtree(vnext_addon.parents[1], ignore_errors=True)


def patch_synthetic_next_shape(addon_dir: Path) -> None:
    error_codes = addon_dir / "utils" / "error_codes.gd"
    text = error_codes.read_text(encoding="utf-8")
    marker = 'const MISSING_REQUIRED_PARAM := "MISSING_REQUIRED_PARAM"\n'
    assert marker in text
    text = text.replace(
        marker,
        marker + 'const SYNTHETIC_NEXT_CONST := "synthetic_next"\n',
        1,
    )
    error_codes.write_text(text, encoding="utf-8")

    handler = addon_dir / "handlers" / "self_update_synthetic_next.gd"
    handler.write_text(
        """@tool
extends RefCounted

const ErrorCodes := preload("res://addons/godot_ai/utils/error_codes.gd")


static func marker() -> String:
\treturn ErrorCodes.SYNTHETIC_NEXT_CONST
""",
        encoding="utf-8",
    )


def test_install_downloaded_update_restarts_live_server(tmp_path: Path) -> None:
    """#918: drive install_downloaded_update() with server start enabled.

    The runner-only forward test stubs ``_start_server()``. This case takes
    the plugin handoff that clears the spawn guard, lets the new plugin
    start a real backend, and asserts ``/godot-ai/status`` is live.
    """
    godot_bin = godot_bin_or_skip()
    smoke = load_smoke_script()
    anchor = tmp_path / "dev-anchor"
    link_dev_checkout_anchor(anchor, ROOT)
    project = anchor / "project"
    base_version = read_plugin_version(PLUGIN_ROOT / "plugin.cfg")
    next_version = smoke.bump_patch_version(base_version)
    server_version = LIVE_SERVER_VERSION

    prepare_project_shell(project)
    write_install_update_driver(project, http_port=LIVE_HTTP_PORT)

    base_addon = project / "addons" / "godot_ai"
    copy_addon_tree(PLUGIN_ROOT, base_addon)
    patch_fixture_addon(
        base_addon,
        version=base_version,
        server_version=server_version,
        next_version=next_version,
        skip_server_start=False,
        http_port=LIVE_HTTP_PORT,
        ws_port=LIVE_WS_PORT,
    )

    vnext_addon = project / ".self-update-vnext" / "addons" / "godot_ai"
    copy_addon_tree(PLUGIN_ROOT, vnext_addon)
    patch_fixture_addon(
        vnext_addon,
        version=next_version,
        server_version=server_version,
        next_version=next_version,
        skip_server_start=False,
        http_port=LIVE_HTTP_PORT,
        ws_port=LIVE_WS_PORT,
    )
    smoke.patch_vnext_hot_reload_trigger(vnext_addon / "mcp_dock.gd")
    patch_synthetic_next_shape(vnext_addon)

    zip_path = project / "_test_update_zip" / TEST_ZIP_NAME
    create_plugin_zip(vnext_addon, zip_path)

    log = run_godot_editor(project, godot_bin, allow_headless=True, timeout=180)

    assert_no_update_parse_errors(log)
    assert "SELF_UPDATE_TEST | calling install_downloaded_update" in log
    assert "SELF_UPDATE_TEST | synthetic handler marker synthetic_next" in log
    assert f"SELF_UPDATE_TEST | status name=godot-ai server_version={server_version}" in log
    assert read_plugin_version(base_addon / "plugin.cfg") == next_version

    status_path = project / POST_UPDATE_STATUS_FILE
    assert status_path.is_file(), log
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload.get("name") == "godot-ai"
    assert payload.get("server_version") == server_version

    shutil.rmtree(vnext_addon.parents[1], ignore_errors=True)
