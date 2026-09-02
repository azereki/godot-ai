@tool
extends Node

## Reload-stable value coordinator. It never opens or mutates package/live
## files and retains no plugin, Dock, or generic owner. The Python actor owns
## every namespace change; this old compiled object only disables, scans,
## enables, and observes durable records.

const PLUGIN_CFG := "res://addons/godot_ai/plugin.cfg"
const POLL_MSEC := 50
const DEADLINE_MSEC := 90 * 1000
const UPDATE_TRANSACTION_ENV := "GODOT_AI_UPDATE_TRANSACTION"
const UPDATE_EDITOR_NONCE_ENV := "GODOT_AI_UPDATE_EDITOR_NONCE"
const UPDATE_ACTOR_HANDOFF_ENV := "GODOT_AI_UPDATE_ACTOR_HANDOFF"
const UPDATE_ACTOR_HANDOFF_SCHEMA := 1
const UPDATE_ACTOR_PROTOCOL_VERSION := 1
const PortResolver := preload("res://addons/godot_ai/utils/port_resolver.gd")
const QualificationBarrier := preload(
	"res://addons/godot_ai/utils/update_qualification_barrier.gd"
)
const UvResolution := preload("res://addons/godot_ai/utils/uv_resolution_policy.gd")

enum Phase { DRAIN, WAIT_STAGE, WAIT_SCAN, WAIT_CLAIM, BARRIER, DONE }

var _command: Array[String] = []
var _prepared: Dictionary = {}
var _editor_nonce := ""
var _phase := Phase.DONE
var _frames := 0
var _actor_pid := -1
var _deadline := 0
var _next_poll := 0
var _qualification := QualificationBarrier.new()
var _barrier_continuation := Callable()
var _barrier_started_msec := 0
var _scan_rollback := false


func start(prepared: Dictionary, command: Array[String], editor_nonce: String) -> void:
	if _phase != Phase.DONE or command.is_empty():
		return
	_prepared = prepared.duplicate(true)
	if not _qualification.configure(_prepared):
		_stop_message(_qualification.error)
		_qualification.clear_environment()
		queue_free()
		return
	_command = command.duplicate()
	_editor_nonce = editor_nonce
	OS.set_environment(UPDATE_TRANSACTION_ENV, str(_prepared.transaction))
	OS.set_environment(UPDATE_EDITOR_NONCE_ENV, editor_nonce)
	OS.set_environment(UPDATE_ACTOR_HANDOFF_ENV, JSON.stringify({
		"schema_version": UPDATE_ACTOR_HANDOFF_SCHEMA,
		"protocol_version": UPDATE_ACTOR_PROTOCOL_VERSION,
		"package_version": str(_prepared.from_version),
		"transaction": str(_prepared.transaction),
		"editor_nonce": editor_nonce,
		"command": _command,
	}))
	_deadline = Time.get_ticks_msec() + DEADLINE_MSEC
	_frames = 2
	_phase = Phase.DRAIN
	set_process(true)


func _process(_delta: float) -> void:
	if _phase == Phase.BARRIER:
		_poll_barrier()
		return
	if Time.get_ticks_msec() >= _deadline:
		_stop("transaction coordinator timed out; explicit repair is required")
		return
	if _phase == Phase.DRAIN:
		_frames -= 1
		if _frames <= 0:
			_barrier("coordinator_disable_request", "before", _disable_plugin)
		return
	if Time.get_ticks_msec() < _next_poll:
		return
	_next_poll = Time.get_ticks_msec() + POLL_MSEC
	if _phase == Phase.WAIT_STAGE:
		var journal := _read_record(_record_path("journal.json"))
		match str(journal.get("phase", "")):
			"stage_live":
				_scan(false)
			"rolled_back":
				_scan(true)
			"repair_required":
				_stop("activation needs explicit repair; plugin remains disabled")
	elif _phase == Phase.WAIT_CLAIM:
		var claim := _read_record(_record_path("claim.json"))
		match str(claim.get("outcome", "")):
			"success":
				_finish()
			"rolled_back":
				EditorInterface.set_plugin_enabled(PLUGIN_CFG, false)
				_scan(true)
			"repair_required":
				EditorInterface.set_plugin_enabled(PLUGIN_CFG, false)
				_stop("activation needs explicit repair; normal startup remains barred")
	if _actor_pid > 1 and not OS.is_process_running(_actor_pid) and _phase == Phase.WAIT_STAGE:
		_stop("transaction actor exited before publishing a live or terminal phase")


func _spawn_actor() -> void:
	var args := _command.slice(1)
	args.append_array([
		"activate",
		"--project", str(_prepared.project_root),
		"--install", str(_prepared.install_root),
		"--recovery-root", str(_prepared.recovery_root),
		"--stage", str(_prepared.stage_root),
		"--transaction", str(_prepared.transaction),
		"--from-version", str(_prepared.from_version),
		"--to-version", str(_prepared.to_version),
		"--manifest-sha256", str(_prepared.manifest_sha256),
		"--editor-pid", str(OS.get_process_id()),
		"--editor-nonce", _editor_nonce,
	])
	PortResolver.lock_process_spawn()
	var saved_uv_environment := (
		UvResolution.isolate_environment()
		if UvResolution.is_production_command(_command)
		else {}
	)
	_actor_pid = _create_actor_process(_command[0], args)
	## The actor inherited the one-shot tuple. The barrier object already copied
	## it for any later coordinator effect, so no later child process needs it.
	_qualification.clear_environment()
	UvResolution.restore_environment(saved_uv_environment)
	PortResolver.unlock_process_spawn()
	if _actor_pid <= 1:
		_recover_spawn_failure()
		return
	_phase = Phase.WAIT_STAGE


func _recover_spawn_failure() -> void:
	## Clear the inherited transaction before re-enabling: otherwise the old
	## tree would enter the initiating-startup path for an activation that never began.
	## Keep the authenticated prepared state intact.  A failed create_process
	## gives us no bounded way to run cleanup from the editor main thread;
	## preflight already fails closed until the operator uses abort-prepared.
	_finish()
	_set_plugin_enabled(true)
	_stop_message(
		"could not launch transaction actor; old plugin re-enabled unchanged; "
		+ "prepared state blocks future updates until explicit abort-prepared"
	)


func _create_actor_process(program: String, args: Array[String]) -> int:
	return OS.create_process(program, args)


func _set_plugin_enabled(enabled: bool) -> void:
	EditorInterface.set_plugin_enabled(PLUGIN_CFG, enabled)


func _plugin_is_enabled() -> bool:
	return EditorInterface.is_plugin_enabled(PLUGIN_CFG)


func _disable_plugin() -> void:
	print("MCP | update coordinator disabling old plugin")
	_set_plugin_enabled(false)
	_barrier("coordinator_disable_request", "after", _verify_disabled)


func _verify_disabled() -> void:
	_barrier("coordinator_disable_verified", "before", _verify_disabled_effect)


func _verify_disabled_effect() -> void:
	if _plugin_is_enabled():
		_stop("transaction coordinator could not verify the old plugin was disabled")
		return
	_barrier("coordinator_disable_verified", "after", _spawn_actor)


func _scan(rollback: bool) -> void:
	_scan_rollback = rollback
	_barrier("coordinator_filesystem_scan", "before", _start_scan)


func _start_scan() -> void:
	_phase = Phase.WAIT_SCAN
	var filesystem := EditorInterface.get_resource_filesystem()
	if not filesystem.filesystem_changed.is_connected(_on_filesystem_changed):
		filesystem.filesystem_changed.connect(_on_filesystem_changed, CONNECT_ONE_SHOT)
	filesystem.scan()


func _on_filesystem_changed() -> void:
	if _phase != Phase.WAIT_SCAN:
		return
	_barrier("coordinator_filesystem_scan", "after", _enable_plugin)


func _enable_plugin() -> void:
	_barrier("coordinator_enable", "before", _enable_plugin_effect)


func _enable_plugin_effect() -> void:
	if not _scan_rollback:
		## The new root's synchronous startup barrier writes readiness, waits
		## for the actor result, and claims it before normal startup can begin.
		print("MCP | update coordinator enabling verified plugin")
		EditorInterface.set_plugin_enabled(PLUGIN_CFG, true)
	else:
		## The environment transaction id lets the restored old root consume
		## the already-claimed rollback outcome before it starts normally.
		print("MCP | update coordinator enabling rolled-back plugin")
		EditorInterface.set_plugin_enabled(PLUGIN_CFG, true)
	_barrier("coordinator_enable", "after", _after_enable)


func _after_enable() -> void:
	if _scan_rollback:
		_finish()
	else:
		_phase = Phase.WAIT_CLAIM


func _barrier(effect: String, when: String, continuation: Callable) -> void:
	if _qualification.begin(effect, when):
		_barrier_continuation = continuation
		_barrier_started_msec = Time.get_ticks_msec()
		_phase = Phase.BARRIER
		return
	if not _qualification.error.is_empty():
		_stop(_qualification.error)
		return
	continuation.call()


func _poll_barrier() -> void:
	var outcome := _qualification.poll()
	if outcome != QualificationBarrier.WAITING:
		_deadline += Time.get_ticks_msec() - _barrier_started_msec
		_barrier_started_msec = 0
	match outcome:
		QualificationBarrier.WAITING:
			return
		QualificationBarrier.CONTINUE:
			var continuation := _barrier_continuation
			_barrier_continuation = Callable()
			_qualification.clear_environment()
			continuation.call()
		QualificationBarrier.INJECT_FAILURE:
			_qualification.clear_environment()
			_stop("qualification failpoint injected; explicit recovery is required")
		_:
			_qualification.clear_environment()
			_stop(_qualification.error)


func _record_path(name: String) -> String:
	return str(_prepared.recovery_root).path_join("transactions").path_join(
		str(_prepared.transaction)
	).path_join(name)


static func _read_record(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}


func _finish() -> void:
	_qualification.clear_environment()
	OS.unset_environment(UPDATE_TRANSACTION_ENV)
	OS.unset_environment(UPDATE_EDITOR_NONCE_ENV)
	OS.unset_environment(UPDATE_ACTOR_HANDOFF_ENV)
	_phase = Phase.DONE
	set_process(false)
	queue_free()


func _stop(message: String) -> void:
	_stop_message(message)
	_finish()


func _stop_message(message: String) -> void:
	push_error("MCP | %s" % message)
