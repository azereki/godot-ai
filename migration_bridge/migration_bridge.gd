@tool
extends Node

## Prepares the embedded canonical v4 release while the migration capsule is
## still enabled. The Python actor authenticates and stages the exact tree;
## this script never writes live add-on files.

const BridgeExec := preload("res://addons/godot_ai/bridge_exec.gd")
const PAYLOAD_ROOT := "res://addons/godot_ai/migration_payload"
const ARCHIVE_NAME := "godot-ai-v4-plugin.zip"
const MANIFEST_NAME := "godot-ai-v4-plugin.manifest.json"
const SIGNATURE_NAME := "godot-ai-v4-plugin.manifest.sig"
const REPOSITORY := "hi-godot/godot-ai"
const PREPARE_TIMEOUT_MSEC := 180 * 1000
const ACTOR_PROTOCOL := 1
const PENDING_V3_UPDATE_SETTING := "godot_ai/pending_self_update_event"

signal state_changed(message: String, failed: bool, termination_unproven: bool)
signal prepared(package: Dictionary)

var _thread: Thread
var _started := false
var _cancel_mutex := Mutex.new()
var _cancelled := false


func start() -> void:
	if _started:
		return
	_started = true
	var identity := _release_identity()
	if identity.is_empty():
		state_changed.emit("The embedded signed v4 release metadata is invalid.", true, false)
		return
	var nonce := Crypto.new().generate_random_bytes(16).hex_encode()
	var transaction := Crypto.new().generate_random_bytes(16).hex_encode()
	var job := {
		"archive": ProjectSettings.globalize_path(PAYLOAD_ROOT.path_join(ARCHIVE_NAME)),
		"manifest": ProjectSettings.globalize_path(PAYLOAD_ROOT.path_join(MANIFEST_NAME)),
		"signature": ProjectSettings.globalize_path(PAYLOAD_ROOT.path_join(SIGNATURE_NAME)),
		"project": ProjectSettings.globalize_path("res://").trim_suffix("/"),
		"install": ProjectSettings.globalize_path("res://addons/godot_ai"),
		"editor_pid": OS.get_process_id(),
		"editor_nonce": nonce,
		"transaction": transaction,
		"from_version": _previous_version(),
		"identity": identity,
	}
	_thread = Thread.new()
	if _thread.start(
		Callable(MigrationBridgeWorker, "prepare").bind(job, Callable(self, "_cancel_requested"))
	) != OK:
		_thread = null
		state_changed.emit("Could not start the v4 migration preparation worker.", true, false)
		return
	set_process(true)


func _process(_delta: float) -> void:
	if _thread == null or _thread.is_alive():
		return
	var result: Variant = _thread.wait_to_finish()
	_thread = null
	set_process(false)
	if not result is Dictionary or not bool(result.get("ok", false)):
		var message := str(result.get("error", "The v4 migration could not be prepared.")) if result is Dictionary else "The v4 migration worker returned no result."
		state_changed.emit(message, true, result is Dictionary and bool(result.get("termination_unproven", false)))
		return
	state_changed.emit("Activating the verified Godot AI v4 tree…", false, false)
	prepared.emit((result as Dictionary).get("package", {}).duplicate(true))


func cancel_and_join() -> bool:
	## Return whether actor termination is proved, including during plugin unload.
	if _thread != null:
		_cancel_mutex.lock()
		_cancelled = true
		_cancel_mutex.unlock()
		var result: Variant = _thread.wait_to_finish()
		_thread = null
		return result is Dictionary and not bool(result.get("termination_unproven", false))
	return true


func _cancel_requested() -> bool:
	_cancel_mutex.lock()
	var cancelled := _cancelled
	_cancel_mutex.unlock()
	return cancelled


func _release_identity() -> Dictionary:
	var path := PAYLOAD_ROOT.path_join(MANIFEST_NAME)
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null or file.get_length() <= 0 or file.get_length() > 1024 * 1024:
		return {}
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	if not parsed is Dictionary:
		return {}
	var tag := str(parsed.get("tag", ""))
	var version := str(parsed.get("version", ""))
	var source := str(parsed.get("source_commit", ""))
	var source_expression := RegEx.new()
	if (
		str(parsed.get("repository", "")) != REPOSITORY
		or str(parsed.get("channel", "")) != "stable"
		or tag != "v%s" % version
		or not tag.begins_with("v4.")
		or source_expression.compile("^[0-9a-f]{40}$") != OK
		or source_expression.search(source) == null
	):
		return {}
	return {"tag": tag, "version": version, "source": source}


static func _previous_version() -> String:
	var settings := EditorInterface.get_editor_settings()
	if settings != null and settings.has_setting(PENDING_V3_UPDATE_SETTING):
		var parsed: Variant = JSON.parse_string(str(settings.get_setting(PENDING_V3_UPDATE_SETTING)))
		if parsed is Dictionary:
			var value := str(parsed.get("from_version", ""))
			if _is_pre_v4_version(value):
				return value
	## Older v3 runners did not all publish the marker. Manual-major client
	## repinning replaces any owned pre-v4 entry, so this fallback is identity
	## metadata rather than a client-selection authority.
	return "3.0.0"


static func _is_pre_v4_version(value: String) -> bool:
	var expression := RegEx.new()
	return expression.compile("^[0-3]\\.\\d+\\.\\d+$") == OK and expression.search(value) != null


class MigrationBridgeWorker:
	static func prepare(job: Dictionary, cancel_check: Callable) -> Dictionary:
		var identity: Dictionary = job.identity
		var version := str(identity.version)
		var command := BridgeExec.actor_command(version)
		if command.is_empty():
			return {"ok": false, "error": "Install uv (which provides uvx), reopen Godot, then click Retry migration."}
		var checked := _call(command, ["identity"], version, PREPARE_TIMEOUT_MSEC, cancel_check)
		if not bool(checked.get("ok", false)):
			return checked
		var common: Array[String] = [
			"--project", str(job.project),
			"--install", str(job.install),
			"--editor-pid", str(job.editor_pid),
			"--editor-nonce", str(job.editor_nonce),
		]
		var lease_arguments: Array[String] = ["lease", "acquire"]
		lease_arguments.append_array(common)
		var lease := _call(
			command, lease_arguments, version, PREPARE_TIMEOUT_MSEC, cancel_check
		)
		if not bool(lease.get("ok", false)):
			return lease
		var arguments: Array[String] = [
			"prepare",
			"--archive", str(job.archive),
			"--manifest", str(job.manifest),
			"--signature", str(job.signature),
			"--project", str(job.project),
			"--install", str(job.install),
			"--transaction", str(job.transaction),
			"--channel", "stable",
			"--tag", str(identity.tag),
			"--version", version,
			"--source", str(identity.source),
			"--editor-pid", str(job.editor_pid),
			"--editor-nonce", str(job.editor_nonce),
		]
		var staged := _call(command, arguments, version, PREPARE_TIMEOUT_MSEC, cancel_check)
		if not bool(staged.get("ok", false)):
			## A timed-out process may still own the lease or be mutating its
			## private stage. Preserve that durable exclusion when termination
			## cannot be proved; startup recovery can then adjudicate it safely.
			if not bool(staged.get("termination_unproven", false)):
				var release_arguments: Array[String] = ["lease", "release"]
				release_arguments.append_array(common)
				_call(
					command,
					release_arguments,
					version,
					PREPARE_TIMEOUT_MSEC,
					Callable(),
				)
			return staged
		var data: Dictionary = staged.data
		return {"ok": true, "package": {
			"actor_command": command,
			"editor_nonce": str(job.editor_nonce),
			"from_version": str(job.from_version),
			"install_root": str(job.install),
			"manifest_sha256": str(data.get("manifest_sha256", "")),
			"project_root": str(job.project),
			"recovery_root": str(data.get("recovery_root", "")),
			"stage_root": str(data.get("stage_root", "")),
			"to_version": version,
			"transaction": str(job.transaction),
		}}


	static func _call(
		command: Array[String],
		arguments: Array[String],
		version: String,
		timeout: int,
		cancel_check: Callable,
	) -> Dictionary:
		var executed := BridgeExec.run(command, arguments, timeout, cancel_check)
		if not bool(executed.get("ok", false)):
			return executed
		var parsed: Variant = JSON.parse_string(str(executed.get("stdout", "")).strip_edges())
		if (
			not parsed is Dictionary
			or int(parsed.get("protocol_version", 0)) != ACTOR_PROTOCOL
			or str(parsed.get("package_version", "")) != version
		):
			return {"ok": false, "error": "The v4 transaction actor identity is incompatible."}
		return {"ok": true, "data": parsed}
