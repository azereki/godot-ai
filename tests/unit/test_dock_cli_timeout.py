"""Source-structure regression tests for the wall-clock-bounded CLI fix.

Issues #238 / #239: a hung `claude mcp list` was wedging the dock's
status refresh worker for 6+ minutes; the Configure / Remove buttons hit
the same root cause on the editor main thread. The fix is layered:

1. `McpCliExec.run` wraps every shell-out in an `OS.execute_with_pipe` +
   poll/exact-process-grant loop with a hard wall-clock budget.
2. `McpCliStrategy` uses the helper from configure / remove / status —
   no direct `OS.execute(..., true)` call survives.
3. The root-owned client-job owner dispatches Configure / Remove to per-row
   workers; the Dock emits intents and paints value snapshots only.

These tests lock the structure in so a future "simplify" pass can't
silently regress either issue.
"""

from __future__ import annotations

from pathlib import Path

from tests.unit._gdscript_text import get_func_block

PLUGIN_ROOT = Path(__file__).resolve().parents[2] / "plugin" / "addons" / "godot_ai"


def test_cli_strategy_routes_every_shell_out_through_mcpcliexec() -> None:
    """No bare OS.execute survives in _cli_strategy.gd."""

    cli_source = (PLUGIN_ROOT / "clients" / "_cli_strategy.gd").read_text(encoding="utf-8")

    # The whole point of the refactor: every CLI invocation must go
    # through the bounded helper. A bare OS.execute slipping back in
    # would re-introduce the hang.
    assert "OS.execute(" not in cli_source, (
        "OS.execute(...) must not appear in _cli_strategy.gd — every "
        "shell-out should go through McpCliExec.run for the wall-clock "
        "timeout. See issues #238 / #239."
    )
    # The replacement should be present in all three call sites
    # (configure, remove, status check) at minimum.
    assert cli_source.count("McpCliExec.run(") >= 3, (
        "Configure, Remove, and check_status_details must each call "
        "McpCliExec.run — fewer call sites means at least one CLI path "
        "is still synchronous."
    )


def test_cli_exec_helper_uses_pipe_spawn_and_exact_process_kill() -> None:
    """The helper must spawn detached and kill on timeout — not a blocking OS.execute."""

    helper_source = (PLUGIN_ROOT / "clients" / "_cli_exec.gd").read_text(encoding="utf-8")

    # Pipe-based spawn returns a PID we can poll on. A blocking
    # OS.execute(..., true) here would just relocate the original hang.
    assert "OS.execute_with_pipe(" in helper_source
    assert "OS.is_process_running(" in helper_source
    assert "capture_process_kill_grant(pid)" in helper_source
    assert "kill_exact_processes([kill_grant], false, true)" in helper_source
    assert "while PortResolver.pid_alive(pid)" in helper_source
    assert "OS.kill(" not in helper_source
    assert "get_as_text()" not in helper_source, (
        "Do not drain OS.execute_with_pipe FileAccess handles with get_as_text(); "
        "on Windows it can emit native PeekNamedPipe errors into Godot's Output panel."
    )
    # Sanity-check the return shape so callers can rely on the four keys.
    for key in (
        "exit_code",
        "stdout",
        "timed_out",
        "spawn_failed",
        "termination_failed",
    ):
        assert f'"{key}"' in helper_source, (
            f"Helper must populate the '{key}' key — callers in _cli_strategy.gd dispatch on it."
        )


def test_posix_timeout_is_honest_about_descendants_and_never_drains_their_pipe() -> None:
    helper_source = (PLUGIN_ROOT / "clients" / "_cli_exec.gd").read_text(encoding="utf-8")
    run = get_func_block(helper_source, "static func _run_piped(")

    assert 'OS.get_name() != "Windows"' in run
    assert "if not termination_failed:" in run
    assert "not killed.has(pid)" in run
    assert run.index("if not termination_failed:") < run.index("_drain_pipe(stdio)")
    assert run.index("termination_failed :=") < run.index(
        '"termination_failed": termination_failed'
    )


def test_cli_strategy_surfaces_timeout_in_configure_and_remove_messages() -> None:
    """A timeout must produce a user-actionable error, not a cryptic exit code."""

    cli_source = (PLUGIN_ROOT / "clients" / "_cli_strategy.gd").read_text(encoding="utf-8")

    # The dock surfaces these strings in its row-error label and "Run
    # this manually" panel. Drift here means the user sees "exit code
    # -1" instead of "timed out — retry by hand."
    assert "Configure" in cli_source and "timed out" in cli_source
    assert "Remove" in cli_source
    # The probe path uses a different label ("probe timed out") because
    # the worker plumbs it into the row's error_msg slot, not into a
    # configure result. Guarding this prevents an over-eager unifier
    # from collapsing the two phrasings and breaking the row UI.
    assert "probe timed out" in cli_source


def test_cli_mutations_stop_and_propagate_when_termination_is_unproven() -> None:
    cli_source = (PLUGIN_ROOT / "clients" / "_cli_strategy.gd").read_text(encoding="utf-8")
    configure = get_func_block(cli_source, "static func _configure_claimed(")
    remove = get_func_block(cli_source, "static func _remove_claimed(")
    status = get_func_block(cli_source, "static func check_status_details(")
    helper = get_func_block(cli_source, "static func _unproven_mutation_failure(")

    assert configure.count("_unproven_mutation_failure(") == 2
    assert configure.index("cleanup_failure") < configure.index("cli_register_template.is_empty()")
    assert "_unproven_mutation_failure(" in remove
    assert '"termination_failed": true' in helper
    assert "MutationLock.recovery_message()" in helper
    assert "_unproven_mutation_failure(" not in status, (
        "read-only probes may report ERROR but must not poison mutation authority"
    )


def test_all_automatic_mutations_hold_one_global_claim_through_verification() -> None:
    configurator_source = (PLUGIN_ROOT / "client_configurator.gd").read_text(encoding="utf-8")
    cli_source = (PLUGIN_ROOT / "clients" / "_cli_strategy.gd").read_text(encoding="utf-8")
    lock_source = (PLUGIN_ROOT / "utils" / "client_mutation_lock.gd").read_text(encoding="utf-8")
    configure = get_func_block(configurator_source, "static func configure(")
    remove = get_func_block(configurator_source, "static func remove(")
    finish = get_func_block(configurator_source, "static func _finish_client_mutation(")
    dispatch_configure = get_func_block(configurator_source, "static func _dispatch_configure(")
    dispatch_remove = get_func_block(configurator_source, "static func _dispatch_remove(")
    status = get_func_block(configurator_source, "static func check_status(")
    status_dispatch = get_func_block(
        configurator_source, "static func _dispatch_check_status_with_cli_path_details("
    )
    acquire = get_func_block(lock_source, "static func acquire(")
    release = get_func_block(lock_source, "static func release(")
    root = get_func_block(lock_source, "static func _prepare_private_root(")
    private_mode = get_func_block(lock_source, "static func _has_private_mode(")

    assert 'MutationLock.acquire(client.id, "configure")' in configure
    assert 'MutationLock.acquire(client.id, "remove")' in remove
    assert (
        configure.index("MutationLock.acquire(")
        < configure.index("_dispatch_configure(")
        < configure.index("_verify_post_state(")
        < configure.index("_finish_client_mutation(")
    )
    assert (
        remove.index("MutationLock.acquire(")
        < remove.index("_dispatch_remove(")
        < remove.index("_verify_post_state(")
        < remove.index("_finish_client_mutation(")
    )
    assert "MutationLock.acquire(" not in cli_source, (
        "the configurator owns the one claim; a nested CLI-only claim would leave "
        "file strategies and the verification interval outside its authority"
    )
    for strategy in ("JsonStrategy", "TomlStrategy", "YamlStrategy", "DshStrategy"):
        assert f"{strategy}.configure(" in dispatch_configure
        assert f"{strategy}.remove(" in dispatch_remove
    assert "MutationLock" not in status
    assert "MutationLock" not in status_dispatch, "read-only status probes stay lock-free"
    assert "OS.get_config_dir()" in lock_source
    assert 'globalize_path("user://")' not in lock_source
    assert "_prepare_private_root()" in acquire
    assert "DirAccess.make_dir_absolute(path)" in acquire
    assert acquire.index("_prepare_private_root()") < acquire.index(
        "DirAccess.make_dir_absolute(path)"
    )
    assert acquire.index("DirAccess.make_dir_absolute(path)") < acquire.index(
        "FileAccess.open(record_path"
    )
    assert acquire.index("_has_private_mode(path)") < acquire.index("FileAccess.open(record_path")
    assert "_is_link(root)" in root
    assert "FileAccess.set_unix_permissions(path, _OWNER_DIRECTORY_MODE)" in private_mode
    assert "actual_mode == _OWNER_DIRECTORY_MODE" in private_mode
    assert "remove_absolute" not in acquire, (
        "a crash/record failure must strand the deny directory, never clean it optimistically"
    )
    assert finish.index('result.get("termination_failed", false)') < finish.index(
        "MutationLock.release(claim)"
    )
    assert "token" in release and "OS.get_process_id()" in release
    assert release.index("remove_absolute(record_path)") < release.index("remove_absolute(path)")
    assert "restarting Godot alone" in lock_source
    assert "explicitly remove" in lock_source

    owner_source = (PLUGIN_ROOT / "utils" / "client_job_owner.gd").read_text(encoding="utf-8")
    ordinary = get_func_block(owner_source, "func _run_action(")
    migration = get_func_block(owner_source, "func _run_post_update_repin(")
    assert "ClientConfigurator.configure(" in ordinary
    assert "ClientConfigurator.remove(" in ordinary
    assert "ClientConfigurator.configure(" in migration, (
        "post-update/M6 must enter the same cross-install authority path as ordinary actions"
    )


def test_client_owner_persists_unproven_mutation_and_blocks_update_quiescence() -> None:
    owner_source = (PLUGIN_ROOT / "utils" / "client_job_owner.gd").read_text(encoding="utf-8")
    request = get_func_block(owner_source, "func _start_action(")
    finalize = get_func_block(owner_source, "func _finalize_action(")
    poll_refresh = get_func_block(owner_source, "func _poll_refresh() -> void:")
    quiesce = get_func_block(owner_source, "func quiesce(")
    post_update = get_func_block(owner_source, "func _run_post_update_repin(")
    begin_post_update = get_func_block(owner_source, "func begin_post_update_repin(")
    init = get_func_block(owner_source, "func _init() -> void:")
    mark = get_func_block(owner_source, "func _mark_mutation_termination_unproven(")

    assert "Engine.get_meta(MUTATION_UNPROVEN_META" in init
    assert "Engine.set_meta(" in mark
    assert "_mutation_termination_unproven.has(client_id)" in request
    assert "MutationLock.recovery_message()" in request
    assert finalize.index("_record_unproven_action_result(") < finalize.index(
        "_action_threads.erase("
    )
    assert "_action_orphans" not in owner_source
    assert "_action_generations" not in owner_source
    assert "_record_unproven_action_payload" in quiesce
    assert poll_refresh.count("var data := payload as Dictionary") == 1
    assert "or MutationLock.is_locked()" in quiesce
    assert '"ok": not termination_unproven' in quiesce
    assert "MutationLock.is_locked()" in begin_post_update
    assert begin_post_update.index("MutationLock.is_locked()") < begin_post_update.index(
        "_post_update_thread != null"
    )
    assert 'prewarm.get("termination_failed", false)' in post_update
    assert post_update.index('prewarm.get("termination_failed", false)') < post_update.index(
        "for probe in probes:"
    )


def test_dock_dispatches_configure_and_remove_to_worker_thread() -> None:
    """Issue #239: the Configure / Remove buttons must not block main."""

    dock_source = (PLUGIN_ROOT / "mcp_dock.gd").read_text(encoding="utf-8")
    owner_source = (PLUGIN_ROOT / "utils" / "client_job_owner.gd").read_text(encoding="utf-8")
    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")

    # Dock intent -> root routing -> one plugin-lifetime worker owner.
    assert "func _dispatch_client_action(" in dock_source
    assert "client_action_requested.emit(" in dock_source
    assert "Thread.new()" not in dock_source
    assert "func request_action(" in owner_source
    assert "Thread.new()" in owner_source
    assert "func _poll_actions(" in owner_source
    assert "_client_jobs.request_action(" in plugin_source
    # The two button handlers should NOT call McpClientConfigurator
    # directly — that would re-introduce the main-thread block. They
    # forward to the dispatcher.
    on_configure = get_func_block(
        dock_source, "func _on_configure_client(client_id: String) -> void:"
    )
    on_remove = get_func_block(dock_source, "func _on_remove_client(client_id: String) -> void:")
    assert "_dispatch_client_action(" in on_configure
    assert "_dispatch_client_action(" in on_remove
    assert "McpClientConfigurator.configure(" not in on_configure, (
        "Configure handler must dispatch to a worker, not call the "
        "configurator inline (issue #239)."
    )
    assert "McpClientConfigurator.remove(" not in on_remove, (
        "Remove handler must dispatch to a worker, not call the configurator inline (issue #239)."
    )


def test_mcp_mutations_share_the_owner_and_have_end_to_end_deferred_headroom() -> None:
    handler_source = (PLUGIN_ROOT / "handlers" / "client_handler.gd").read_text(encoding="utf-8")
    owner_source = (PLUGIN_ROOT / "utils" / "client_job_owner.gd").read_text(encoding="utf-8")
    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")
    python_handler = (
        PLUGIN_ROOT.parents[2] / "src" / "godot_ai" / "handlers" / "client.py"
    ).read_text(encoding="utf-8")
    batch_source = (PLUGIN_ROOT / "handlers" / "batch_handler.gd").read_text(encoding="utf-8")
    request = get_func_block(handler_source, "func _request_client_action(")
    finalize = get_func_block(owner_source, "func _finalize_action(")
    deferred_budget = get_func_block(owner_source, "static func _mcp_action_deferred_timeout_msec(")

    assert "McpClientConfigurator.configure(" not in handler_source
    assert "McpClientConfigurator.remove(" not in handler_source
    assert "_client_jobs.request_mcp_action(" in request
    assert '"_deferred": true' in request
    assert '"_deferred_timeout_ms"' in request
    assert "signal mcp_action_completed" in owner_source
    assert "mcp_action_completed.emit(" in finalize
    assert "mcp_action_completed.connect(_on_mcp_client_action_completed)" in plugin_source
    assert "send_deferred_response(request_id, payload)" in plugin_source
    assert "request_id.is_empty()" in owner_source
    assert 'result.get("status") == "ok" and prewarm_after_configure' in owner_source
    assert "const ACTION_TIMEOUT_MSEC := 75 * 1000" in owner_source
    assert "ACTION_TIMEOUT_MSEC + MCP_ACTION_DEFERRED_GRACE_MSEC" in deferred_budget
    assert "PREWARM_TIMEOUT_MS" not in deferred_budget
    assert "CLIENT_CONFIGURE_TIMEOUT_SECONDS = 85.0" in python_handler
    assert "CLIENT_REMOVE_TIMEOUT_SECONDS = 85.0" in python_handler
    assert '"configure_client"' in batch_source and '"remove_client"' in batch_source


def test_root_owned_workers_quiesce_during_update_and_plugin_exit() -> None:
    """One owner, not the replaceable Dock, drains both worker pools."""

    owner_source = (PLUGIN_ROOT / "utils" / "client_job_owner.gd").read_text(encoding="utf-8")
    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")

    assert "func quiesce(" in owner_source
    quiesce = get_func_block(owner_source, "func quiesce(")
    assert "_refresh_thread.wait_to_finish()" in quiesce
    assert "_post_update_thread.wait_to_finish()" in quiesce
    assert "_action_threads.values()" in quiesce
    install_block = get_func_block(plugin_source, "func install_downloaded_update(")
    assert "_client_jobs.quiesce(" in install_block
    assert install_block.index("_client_jobs.quiesce(") < install_block.index(
        "UpdateCoordinator.new()"
    )
    prepare = get_func_block(plugin_source, "func prepare_for_update_reload()")
    assert "_vision_routing.shutdown()" in prepare
    assert "_dispatcher.quiesce_for_script_swap()" in prepare
    assert prepare.index("_lifecycle.prepare_for_update_reload()") < prepare.index(
        "_vision_routing.shutdown()"
    )
    assert prepare.index("_dispatcher.quiesce_for_script_swap()") < prepare.index(
        "_dispatcher.clear()"
    )
    assert "var script_quiesced := prepare_for_update_reload()" in install_block
    assert install_block.index("prepare_for_update_reload()") < install_block.index(
        "UpdateCoordinator.new()"
    )
    exit_block = get_func_block(plugin_source, "func _exit_tree() -> void:")
    assert "_client_jobs.quiesce()" in exit_block
    assert exit_block.rindex("_release_update_lease()") > exit_block.index(
        "_lifecycle.teardown_for_editor_exit()"
    )


def test_composition_and_post_update_barriers_precede_every_normal_start_effect() -> None:
    """Endpoint probes, client work, update discovery, and server start have one release seam."""

    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")
    enter = get_func_block(plugin_source, "func _enter_tree() -> void:")
    compose = get_func_block(
        plugin_source,
        "func _continue_enter_tree_after_update_barrier() -> void:",
    )
    begin = get_func_block(plugin_source, "func _begin_startup_release() -> void:")
    release = get_func_block(plugin_source, "func _release_normal_startup() -> void:")

    assert "_start_update_startup_barrier()" in enter
    assert "_continue_enter_tree_after_update_barrier()" in enter
    assert enter.index("warm_update_actor_discovery_env()") < enter.index(
        "_start_update_startup_barrier()"
    )
    assert compose.index("add_control_to_dock(") < compose.index("_resolve_ws_port(")
    assert compose.index("_resolve_ws_port(") < compose.index("_begin_startup_release()")
    assert "_client_jobs.activate()" not in compose
    assert "_start_server()" not in compose
    assert "check_for_updates" not in compose
    assert "begin_post_update_repin(" in begin
    assert 'get("manual_migration", false)' in begin
    for effect in (
        "_client_jobs.activate()",
        "_update_manager.check_for_updates.call_deferred()",
        "_start_server()",
        "record_dock_startup()",
    ):
        assert effect in release
    assert release.count("_start_server()") == 1


def test_pending_migration_is_a_root_authority_gate_for_every_start_path() -> None:
    """M6 release state is enforced below the UI; STOP deliberately stays available."""

    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")
    dock_source = (PLUGIN_ROOT / "mcp_dock.gd").read_text(encoding="utf-8")
    snapshot = get_func_block(plugin_source, "func _lifecycle_snapshot_for_dock()")
    lifecycle_action = get_func_block(
        plugin_source,
        "func _on_dock_lifecycle_action_requested(action: int) -> void:",
    )
    dev_action = get_func_block(
        plugin_source,
        "func _on_dock_dev_server_action_requested(action: int) -> void:",
    )
    internal_start = get_func_block(plugin_source, "func _start_server() -> void:")

    assert 'snapshot["normal_start_released"] = _normal_start_released' in snapshot
    assert "_normal_start_released and _lifecycle.can_restart_managed_server()" in snapshot
    assert lifecycle_action.index("if not _normal_start_released:") < lifecycle_action.index(
        "match action:"
    )
    assert "action != Dock.DevServerAction.STOP and not _normal_start_released" in dev_action
    assert dev_action.index("not _normal_start_released") < dev_action.index("match action:")
    assert internal_start.index("if not _normal_start_released:") < internal_start.index(
        "_lifecycle.start_server()"
    )
    for signature, effect in (
        ("func restart_or_start_managed_server() -> bool:", "has_managed_server()"),
        ("func force_restart_server() -> bool:", "_lifecycle.force_restart_server()"),
        ("func recover_incompatible_server(", "_lifecycle.request_replacement()"),
    ):
        block = get_func_block(plugin_source, signature)
        assert block.index("if not _normal_start_released:") < block.index(effect)

    update_buttons = get_func_block(dock_source, "func _update_dev_section_buttons() -> void:")
    assert 'get("normal_start_released", false)' in update_buttons
    assert update_buttons.index("elif not normal_start_released:") < update_buttons.index(
        'text = "Server Start Blocked"'
    )


def test_actor_spawn_failure_never_runs_unbounded_cleanup_on_the_editor_thread() -> None:
    coordinator_source = (PLUGIN_ROOT / "utils" / "update_coordinator.gd").read_text(
        encoding="utf-8"
    )
    recover = get_func_block(coordinator_source, "func _recover_spawn_failure() -> void:")

    assert "OS.execute(" not in coordinator_source
    assert "abort-prepared" in recover
    assert recover.index("_finish()") < recover.index("_set_plugin_enabled(true)")
    assert "prepared state blocks future updates" in recover


def test_manual_major_marker_is_deny_only_and_removed_before_server_start() -> None:
    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")
    parse = get_func_block(plugin_source, "static func _parse_manual_migration_marker(")
    complete = get_func_block(plugin_source, "func _complete_post_update_startup() -> void:")

    assert "MANUAL_MIGRATION_MARKER_SCHEMA" in parse
    assert "source_commit.length() != 40" in parse
    assert "str(parsed.to_version) != loaded_version" in parse
    assert "_remove_manual_migration_marker()" in complete
    assert complete.index("_remove_manual_migration_marker()") < complete.index(
        "_release_normal_startup()"
    )


def test_hot_update_migration_is_durably_acknowledged_before_normal_start() -> None:
    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")
    repin = get_func_block(plugin_source, "func _on_post_update_repin_completed(")
    complete = get_func_block(plugin_source, "func _complete_post_update_startup() -> void:")
    present_complete = get_func_block(
        plugin_source, "func _present_post_update_complete() -> void:"
    )
    start = get_func_block(plugin_source, "func _start_post_update_completion() -> bool:")
    worker = get_func_block(
        plugin_source,
        "static func _run_post_update_completion_job(",
    )
    process = get_func_block(plugin_source, "func _process(_delta: float) -> void:")

    assert "_complete_post_update_startup()" in repin
    assert '"continue"' not in repin
    assert "_start_post_update_completion()" in complete
    assert complete.index("_start_post_update_completion()") < complete.index(
        "_release_normal_startup()"
    )
    assert 'var arguments: Array[String] = ["complete-migration"]' in start
    assert '"--recovery-root"' in start
    assert "_migration_completion_matches(" in worker
    completion_poll = process.index('job == "migration_completion"')
    assert process.index('get("ok", false)', completion_poll) < process.index(
        "_release_normal_startup()", completion_poll
    )
    assert '"banner_visible": false' in present_complete
    assert process.index("_present_post_update_complete()", completion_poll) < process.index(
        "_release_normal_startup()", completion_poll
    )


def test_post_update_terminal_vocabulary_and_failed_quiescence_rebuild_are_explicit() -> None:
    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")
    fan = get_func_block(plugin_source, "func _fan_post_update_outcome() -> void:")
    prepare = get_func_block(plugin_source, "func prepare_for_update_reload() -> Dictionary:")
    install = get_func_block(plugin_source, "func install_downloaded_update(")

    for status in ("success", "failed_clean", "failed_mixed", "unknown"):
        assert f'"{status}"' in fan
    assert 'status = "failed"' not in fan
    assert 'quiesced["reload_required"] = true' in prepare
    assert "_reload_plugin_after_failed_update.call_deferred()" in install


def test_update_downloads_use_one_actor_allocated_private_directory() -> None:
    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")
    manager_source = (PLUGIN_ROOT / "utils" / "update_manager.gd").read_text(encoding="utf-8")
    preflight = get_func_block(plugin_source, "func _preflight_update() -> Dictionary:")
    install = get_func_block(plugin_source, "func install_downloaded_update(")

    assert '"--download-id"' in preflight
    assert 'data.get("download_root", "")' in preflight
    assert 'path_join("downloads").path_join(download_id)' in preflight
    assert "TEMP_DIR" not in manager_source
    assert 'preflight.get("download_root", "")' in manager_source
    assert "make_dir_recursive" not in manager_source
    assert "discard_downloads()" in install
    assert "func _directory_is_empty(" in manager_source
    assert "func cancel_install()" in manager_source


def test_actorless_editor_fails_closed_before_it_can_offer_updates() -> None:
    """A mixed-availability twin must not become an invisible live editor."""

    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")
    prepare = get_func_block(plugin_source, "func _prepare_update_startup_barrier() -> Dictionary:")
    job = get_func_block(plugin_source, "func _run_update_startup_barrier_job(")
    enter = get_func_block(plugin_source, "func _enter_tree() -> void:")
    block = get_func_block(plugin_source, "func _block_update_startup() -> void:")
    disable = get_func_block(plugin_source, "func _disable_after_update_barrier() -> void:")

    assert "ClientConfigurator.get_update_transaction_command()" not in prepare
    assert "ClientConfigurator.get_update_transaction_command()" in job
    assert "if command.is_empty():" in job
    assert "refusing swapped-tree startup" in prepare
    assert "refusing unleased plugin startup" in job
    assert "return transaction.is_empty()" not in prepare
    assert "_start_update_startup_barrier()" in enter
    assert "_block_update_startup()" in enter
    assert "_disable_after_update_barrier.call_deferred()" in block
    assert 'set_plugin_enabled("res://addons/godot_ai/plugin.cfg", false)' in disable


def test_headless_export_leases_before_its_early_return_and_releases_on_exit() -> None:
    """Headless export code must join the same-install editor census."""

    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")
    enter = get_func_block(plugin_source, "func _enter_tree() -> void:")
    compose = get_func_block(
        plugin_source,
        "func _continue_enter_tree_after_update_barrier() -> void:",
    )
    exit_block = get_func_block(plugin_source, "func _exit_tree() -> void:")
    headless_exit = exit_block[exit_block.index("if _headless_disabled:") :]

    assert enter.index("if _mcp_disabled_for_headless_launch():") < enter.index(
        "_run_update_startup_barrier()"
    )
    assert "_continue_enter_tree_after_update_barrier()" in enter
    assert compose.index("ExportPlugin.new()") < compose.index(
        "if _mcp_disabled_for_headless_launch():"
    )
    assert headless_exit.index("_release_update_lease()") < headless_exit.index("return")


def test_reload_startup_uses_the_frozen_old_actor_not_new_version_discovery() -> None:
    """The swapped tree must not hit uvx/network while the old actor waits."""

    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")
    coordinator_source = (PLUGIN_ROOT / "utils" / "update_coordinator.gd").read_text(
        encoding="utf-8"
    )
    prepare = get_func_block(plugin_source, "func _prepare_update_startup_barrier() -> Dictionary:")
    job = get_func_block(plugin_source, "func _run_update_startup_barrier_job(")
    execute = get_func_block(plugin_source, "func _execute_update_command(")
    execute_value = get_func_block(plugin_source, "static func _execute_update_command_value(")
    identity = get_func_block(plugin_source, "static func _update_actor_identity_matches(")
    finish = get_func_block(coordinator_source, "func _finish() -> void:")

    assert "_parse_update_actor_handoff(" in prepare
    assert 'command.assign(handoff.get("command", []))' in prepare
    assert 'handoff.get("package_version", "")' in prepare
    assert '"discover_command": transaction.is_empty()' in prepare
    assert 'job.get("discover_command", false)' in job
    assert "_execute_update_command_value(" in job
    assert "frozen_command.duplicate()" in execute
    assert "_update_actor_identity_matches(data, expected_package_version)" in execute_value
    assert 'data.get("protocol_version", 0)' in identity
    assert 'data.get("package_version", "")' in identity
    assert '"protocol_version": UPDATE_ACTOR_PROTOCOL_VERSION' in coordinator_source
    assert '"package_version": str(_prepared.from_version)' in coordinator_source
    assert "OS.set_environment(UPDATE_ACTOR_HANDOFF_ENV, JSON.stringify({" in coordinator_source
    assert "OS.unset_environment(UPDATE_ACTOR_HANDOFF_ENV)" in finish


def test_startup_rejects_a_preloaded_old_instance_even_after_lock_release() -> None:
    """Loaded A may pause while disk becomes B; the first barrier check catches it."""

    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")
    enter = get_func_block(plugin_source, "func _enter_tree() -> void:")
    prepare = get_func_block(plugin_source, "func _prepare_update_startup_barrier() -> Dictionary:")

    assert "_loaded_plugin_version = get_plugin_version()" in enter
    version_check = prepare.index("_loaded_update_version_matches(")
    lock_or_handoff_check = prepare.index("OS.get_environment(UPDATE_TRANSACTION_ENV)")
    assert version_check < lock_or_handoff_check
    assert '"current_version": _loaded_plugin_version' in prepare


def test_update_actor_invocations_are_bounded_and_interactive_startup_is_off_main_thread() -> None:
    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")
    enter = get_func_block(plugin_source, "func _enter_tree() -> void:")
    start = get_func_block(plugin_source, "func _start_update_startup_barrier() -> bool:")
    execute = get_func_block(plugin_source, "func _execute_update_command(")
    execute_value = get_func_block(plugin_source, "static func _execute_update_command_value(")
    accept = get_func_block(plugin_source, "func _accept_update_startup_result(")
    cancel = get_func_block(plugin_source, "func _cancel_update_actor_thread() -> void:")
    refusal = get_func_block(plugin_source, "static func _update_actor_refusal_message(")
    process = get_func_block(plugin_source, "func _process(_delta: float) -> void:")
    exit_block = get_func_block(plugin_source, "func _exit_tree() -> void:")
    release = get_func_block(plugin_source, "func _release_update_lease() -> void:")

    assert "OS.execute(" not in plugin_source
    assert "CliExec.run(" in execute_value
    assert "timeout_ms" in execute_value
    assert "cancel_check" in execute_value
    assert "termination_failed" in execute_value
    assert 'executed.get("stderr", "")' in execute_value
    assert 'executed.get("output", "")' not in execute_value
    assert "UPDATE_ACTOR_ERROR_PREFIX" in refusal
    assert "MAX_UPDATE_ACTOR_ERROR_BYTES" in refusal
    assert "unicode_at" in refusal
    assert "Thread.new()" in start
    assert "_run_update_startup_barrier_job" in start
    assert "ClientConfigurator.get_update_transaction_command()" not in start
    assert "_start_update_startup_barrier()" in enter
    assert enter.index("_mcp_disabled_for_headless_launch()") < enter.index(
        "_run_update_startup_barrier()"
    )
    assert "wait_to_finish()" in process
    assert "_continue_enter_tree_after_update_barrier()" in process
    assert execute.index("_update_actor_termination_unproven") < execute.index(
        "ClientConfigurator.get_update_transaction_command()"
    )
    assert '"termination_unproven": true' in execute
    assert 'checked.get("termination_unproven", false)' in execute
    assert 'result.get("termination_unproven", false)' in accept
    assert 'result.get("termination_unproven", false)' in cancel
    assert exit_block.index("_cancel_update_actor_thread()") < exit_block.rindex(
        "_release_update_lease()"
    )
    assert "_update_actor_termination_unproven" in release


def test_dock_action_dispatch_gates_on_self_update_in_progress() -> None:
    """The same gate the refresh worker honors must protect Configure / Remove."""

    dock_source = (PLUGIN_ROOT / "mcp_dock.gd").read_text(encoding="utf-8")
    block = get_func_block(dock_source, "func _dispatch_client_action(")
    assert "_is_self_update_in_progress" in block, (
        "Configure / Remove dispatch must short-circuit during the "
        "install-update window — a worker mid-call into a half-overwritten "
        "_cli_strategy.gd SIGABRTs (same root cause as the refresh-worker "
        "gate in #235). The flag lives on McpUpdateManager; the dock's "
        "gate consults it via `_is_self_update_in_progress()`."
    )


def test_status_refresh_apply_skips_rows_with_in_flight_action() -> None:
    """A concurrent refresh result must not stomp the 'Configuring…' badge."""

    dock_source = (PLUGIN_ROOT / "mcp_dock.gd").read_text(encoding="utf-8")
    apply_block = get_func_block(dock_source, "func present_client_status_refresh_results(")
    assert "var busy := _busy_client_actions()" in apply_block
    assert "if busy.has(" in apply_block


def test_dock_keeps_only_value_edges_to_root_owned_runtime_state() -> None:
    """The replaceable view must not retain plugin, transport, or log owners."""

    dock_source = (PLUGIN_ROOT / "mcp_dock.gd").read_text(encoding="utf-8")
    log_viewer_source = (PLUGIN_ROOT / "dock_panels" / "log_viewer.gd").read_text(encoding="utf-8")
    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")

    for field in ("var _plugin", "var _connection", "var _log_buffer"):
        assert field not in dock_source
    assert "var _log_buffer" not in log_viewer_source
    for method in (
        "get_server_status(",
        "recover_incompatible_server(",
        "force_restart_server(",
        "restart_or_start_managed_server(",
        "stop_managed_server(",
        "has_managed_server(",
    ):
        assert method not in dock_source
    assert "signal status_snapshot_requested" in dock_source
    assert "func present_transport_snapshot(" in dock_source
    assert "func present_lifecycle_snapshot(" in dock_source
    assert "func present_log_snapshot(" in dock_source
    assert "_dock.present_transport_snapshot(" in plugin_source
    assert "_dock.present_lifecycle_snapshot(" in plugin_source


def test_dock_emits_endpoint_setting_values_and_root_owns_persistence() -> None:
    dock_source = (PLUGIN_ROOT / "mcp_dock.gd").read_text(encoding="utf-8")
    plugin_source = (PLUGIN_ROOT / "plugin.gd").read_text(encoding="utf-8")
    configurator_source = (PLUGIN_ROOT / "client_configurator.gd").read_text(encoding="utf-8")

    assert "signal settings_apply_requested(changes: Dictionary, reload: bool)" in dock_source
    for setting in (
        "SETTING_HTTP_PORT",
        "SETTING_EXCLUDED_DOMAINS",
        "SETTING_TELEMETRY_ENABLED",
        "SETTING_ALLOW_HOSTS",
    ):
        assert f"set_setting(McpSettings.{setting}" not in dock_source
    assert "settings_apply_requested.connect(_on_dock_settings_apply_requested)" in plugin_source
    routed = get_func_block(
        plugin_source,
        "func _on_dock_settings_apply_requested(changes: Dictionary, reload: bool) -> void:",
    )
    assert "ClientConfigurator.apply_endpoint_settings(changes.duplicate(true))" in routed
    assert "func apply_endpoint_settings(changes: Dictionary) -> Dictionary:" in configurator_source
