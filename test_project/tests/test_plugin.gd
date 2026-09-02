@tool
extends McpTestSuite

const GodotAiPlugin := preload("res://addons/godot_ai/plugin.gd")
const PortResolver := preload("res://addons/godot_ai/utils/port_resolver.gd")


func suite_name() -> String:
	return "plugin"


func test_v4_requires_godot_4_7_or_newer_within_4_x() -> void:
	assert_false(GodotAiPlugin._supports_godot_version({"major": 4, "minor": 5}))
	assert_false(GodotAiPlugin._supports_godot_version({"major": 4, "minor": 6}))
	assert_true(GodotAiPlugin._supports_godot_version({"major": 4, "minor": 7}))
	assert_true(GodotAiPlugin._supports_godot_version({"major": 4, "minor": 8}))
	assert_false(GodotAiPlugin._supports_godot_version({"major": 5, "minor": 0}))
	assert_false(GodotAiPlugin._supports_godot_version({}))


func test_headless_launch_disables_mcp_by_default() -> void:
	assert_true(
		GodotAiPlugin._mcp_disabled_for_headless(PackedStringArray(["--headless", "--editor"]), "", ""),
		"--headless must disable MCP startup by default"
	)
	assert_true(
		GodotAiPlugin._mcp_disabled_for_headless(PackedStringArray(["--editor"]), "headless", ""),
		"headless DisplayServer must disable MCP startup by default"
	)


func test_headless_launch_allows_explicit_override() -> void:
	assert_false(
		GodotAiPlugin._mcp_disabled_for_headless(PackedStringArray(["--headless", "--editor"]), "headless", "1"),
		"GODOT_AI_ALLOW_HEADLESS=1 must preserve CI/headless MCP sessions"
	)
	assert_false(
		GodotAiPlugin._mcp_disabled_for_headless(PackedStringArray(["--headless", "--editor"]), "headless", "true"),
		"truthy GODOT_AI_ALLOW_HEADLESS values must preserve MCP startup"
	)


func test_display_driver_headless_args_disable_mcp() -> void:
	assert_true(
		GodotAiPlugin._mcp_disabled_for_headless(PackedStringArray(["--display-driver", "headless"]), "", ""),
		"--display-driver headless must disable MCP startup"
	)
	assert_true(
		GodotAiPlugin._mcp_disabled_for_headless(PackedStringArray(["--display-driver=headless"]), "", ""),
		"--display-driver=headless must disable MCP startup"
	)


func test_update_actor_handoff_is_exact_bounded_and_versioned() -> void:
	var transaction := "0123456789abcdef0123456789abcdef"
	var nonce := "fedcba9876543210fedcba9876543210"
	var executable := ProjectSettings.globalize_path("res://frozen-actor")
	var valid := {
		"schema_version": 1,
		"protocol_version": 1,
		"package_version": "4.0.0",
		"transaction": transaction,
		"editor_nonce": nonce,
		"command": [executable, "-m", "godot_ai.update_transaction"],
	}
	assert_eq(
		GodotAiPlugin._parse_update_actor_handoff(JSON.stringify(valid), transaction, nonce),
		{
			"command": valid.command,
			"package_version": "4.0.0",
			"protocol_version": 1,
		},
	)
	for invalid in [
		valid.merged({"schema_version": 2}, true),
		valid.merged({"protocol_version": 2}, true),
		valid.merged({"package_version": ""}, true),
		valid.merged({"transaction": "other"}, true),
		valid.merged({"editor_nonce": "other"}, true),
		valid.merged({"command": ["relative-actor"]}, true),
		valid.merged({"command": [executable, "bad\nargument"]}, true),
		valid.merged({"surprise": true}, true),
	]:
		assert_true(
			GodotAiPlugin._parse_update_actor_handoff(
				JSON.stringify(invalid), transaction, nonce
			).is_empty()
		)


func test_stale_loaded_plugin_never_crosses_update_barrier() -> void:
	assert_true(GodotAiPlugin._loaded_update_version_matches("4.0.1", "4.0.1"))
	assert_false(GodotAiPlugin._loaded_update_version_matches("4.0.0", "4.0.1"))
	assert_false(GodotAiPlugin._loaded_update_version_matches("", "4.0.1"))


func test_update_actor_response_requires_exact_protocol_and_package() -> void:
	var valid := {"protocol_version": 1, "package_version": "4.0.0", "status": "none"}
	assert_true(GodotAiPlugin._update_actor_identity_matches(valid, "4.0.0"))
	assert_false(GodotAiPlugin._update_actor_identity_matches(valid, "4.0.1"))
	assert_false(GodotAiPlugin._update_actor_identity_matches(
		valid.merged({"protocol_version": 2}, true), "4.0.0"
	))
	assert_false(GodotAiPlugin._update_actor_identity_matches(
		{"status": "none"}, "4.0.0"
	))


func test_update_outcome_is_bound_to_ordinary_or_handoff_startup() -> void:
	var transaction := "0123456789abcdef"
	assert_true(GodotAiPlugin._update_outcome_matches_startup({"status": "none"}, ""))
	assert_true(GodotAiPlugin._update_outcome_matches_startup(
		{"status": "migration_pending", "transaction": transaction}, ""
	))
	assert_false(GodotAiPlugin._update_outcome_matches_startup(
		{"status": "migration_pending", "transaction": ""}, ""
	))
	assert_false(GodotAiPlugin._update_outcome_matches_startup(
		{"status": "claimed", "transaction": transaction}, ""
	))
	assert_false(GodotAiPlugin._update_outcome_matches_startup({"status": "none"}, transaction))
	assert_false(GodotAiPlugin._update_outcome_matches_startup(
		{"status": "claimed", "transaction": "other"}, transaction
	))
	assert_true(GodotAiPlugin._update_outcome_matches_startup(
		{"status": "claimed", "transaction": transaction}, transaction
	))
	assert_true(GodotAiPlugin._migration_completion_matches(
		{"status": "migration_complete", "transaction": transaction}, transaction
	))
	assert_false(GodotAiPlugin._migration_completion_matches(
		{"status": "migration_complete", "transaction": "other"}, transaction
	))


func test_resolve_ws_port_from_output_skips_reserved_configured_port() -> void:
	var output := """
Protocol tcp Port Exclusion Ranges

Start Port    End Port
----------    --------
    9491          9590
    9591          9690
"""
	assert_eq(
		PortResolver.resolve_ws_port_from_output(9500, output, McpClientConfigurator.MAX_PORT),
		9691,
		"configured WS port inside adjacent excluded ranges should move to first clear port",
	)


func test_resolve_ws_port_from_output_keeps_unreserved_configured_port() -> void:
	var output := """
Protocol tcp Port Exclusion Ranges

Start Port    End Port
----------    --------
    9491          9590
"""
	assert_eq(
		PortResolver.resolve_ws_port_from_output(10500, output, McpClientConfigurator.MAX_PORT),
		10500,
		"unreserved configured WS port should stay stable",
	)


func test_pid_alive_rejects_zombie_children() -> void:
	## Regression guard for the zombie-blindness that defeated the first
	## draft of the retry wiring: `kill -0` returns success for BOTH
	## running and zombie processes, and Godot never `waitpid`s on its
	## `OS.create_process` children. A fast-failing uvx launcher would
	## linger as a zombie, `_pid_alive` would report true forever, and
	## the "launcher died" branch in `_check_server_health` (which
	## gates both CRASHED transitions and the --refresh retry) would
	## never fire. See #172.
	if OS.get_name() == "Windows":
		## Windows doesn't have POSIX zombies — `tasklist` shows the
		## process as gone the moment it exits.
		skip("zombie semantics are POSIX-specific")
		return
	var pid := OS.create_process("sleep", ["0"])
	assert_gt(pid, 0, "must successfully spawn the sleep child")
	## Give the child time to exit and enter zombie state (waiting for
	## its parent — us — to reap it). 300ms is generous for a `sleep 0`
	## that exits essentially instantly; under load 100ms can be flaky.
	OS.delay_msec(300)
	assert_false(
		McpPortResolver.pid_alive(pid),
		"zombie (exited, unreaped) child must NOT be reported as alive",
	)


func test_pid_alive_reports_running_process_as_alive() -> void:
	## Positive case: our own process PID must be reported alive. Pairs
	## with the zombie test — catches a regression where the ps-based
	## check became too strict (e.g. rejects normal sleeping processes).
	var own_pid := OS.get_process_id()
	assert_gt(own_pid, 0, "sanity: OS.get_process_id must return a positive pid")
	assert_true(
		McpPortResolver.pid_alive(own_pid),
		"the test runner's own process must be reported as alive",
	)


func test_pid_alive_returns_false_for_nonexistent_pid() -> void:
	## PID 1 (init/launchd) always exists on any running POSIX system, so
	## use a high PID that's essentially guaranteed free. `ps` exits non-zero
	## when the PID doesn't exist, which must map to false, not true.
	assert_false(
		McpPortResolver.pid_alive(2147483646),
		"a non-existent PID must be reported as dead",
	)
	assert_false(McpPortResolver.pid_alive(0), "pid <= 0 is never alive")
	assert_false(McpPortResolver.pid_alive(-1), "negative pid is never alive")
