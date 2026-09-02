@tool
extends RefCounted

## Small bounded process helper for the temporary migration capsule. The
## permanent v4 tree uses McpCliExec; keeping this helper capsule-local avoids
## importing the v3 or v4 runtime graph into the transition plugin.

const POLL_MSEC := 50
const MAX_OUTPUT_BYTES := 64 * 1024
const PUBLIC_INDEX := "https://pypi.org/simple"
const PUBLIC_FLAT_INDEX := "https://pypi.org/simple/godot-ai/"
const UV_ENVIRONMENT := [
	"UV_INDEX", "UV_DEFAULT_INDEX", "UV_INDEX_URL", "UV_EXTRA_INDEX_URL",
	"UV_FIND_LINKS", "UV_INDEX_STRATEGY", "UV_KEYRING_PROVIDER",
	"UV_CONFIG_FILE", "UV_CONSTRAINT", "UV_BUILD_CONSTRAINT", "UV_OVERRIDE",
	"UV_NO_CONFIG", "UV_NO_SOURCES", "UV_NO_BUILD", "UV_NO_BINARY",
	"UV_NO_BINARY_PACKAGE", "UV_NO_VERIFY_HASHES", "UV_PRERELEASE",
	"UV_RESOLUTION", "UV_FORK_STRATEGY", "UV_EXCLUDE_NEWER",
	"UV_EXCLUDE_NEWER_PACKAGE", "UV_INSECURE_HOST", "UV_SYSTEM_CERTS",
	"UV_NATIVE_TLS", "UV_PYTHON", "UV_PYTHON_DOWNLOADS", "UV_PROJECT",
	"UV_WORKING_DIR", "UV_ENV_FILE", "UV_CACHE_DIR", "UV_TOOL_DIR",
	"UV_TOOL_BIN_DIR", "UV_LINK_MODE", "UV_REFRESH", "UV_REFRESH_PACKAGE",
	"UV_REINSTALL", "UV_REINSTALL_PACKAGE", "UV_NO_PROGRESS",
]


static func actor_command(version: String) -> Array[String]:
	var uvx := find_uvx()
	if uvx.is_empty():
		return []
	return [
		uvx,
		"--isolated", "--no-config", "--no-env-file", "--no-sources", "--no-build",
		"--index-strategy", "first-index", "--keyring-provider", "disabled",
		"--index", PUBLIC_INDEX,
		"--default-index", PUBLIC_INDEX,
		"--find-links", PUBLIC_FLAT_INDEX,
		"--from", "godot-ai==%s" % version,
		"godot-ai-update-transaction",
	]


static func find_uvx() -> String:
	var executable := "uvx.exe" if OS.get_name() == "Windows" else "uvx"
	var candidates: Array[String] = []
	var home := OS.get_environment("USERPROFILE") if OS.get_name() == "Windows" else OS.get_environment("HOME")
	if not home.is_empty():
		candidates.append(home.path_join(".local/bin").path_join(executable))
		candidates.append(home.path_join(".cargo/bin").path_join(executable))
	if OS.get_name() == "macOS":
		candidates.append_array([
			"/opt/homebrew/bin/uvx",
			"/usr/local/bin/uvx",
			"/usr/bin/uvx",
		])
	elif OS.get_name() != "Windows":
		candidates.append_array(["/usr/local/bin/uvx", "/usr/bin/uvx"])
	var separator := ";" if OS.get_name() == "Windows" else ":"
	for directory in OS.get_environment("PATH").split(separator, false):
		candidates.append(String(directory).path_join(executable))
	for candidate in candidates:
		if FileAccess.file_exists(candidate):
			return candidate
	return ""


static func run(
	command: Array[String],
	arguments: Array[String],
	timeout_msec: int,
	cancel_check: Callable = Callable(),
) -> Dictionary:
	if command.is_empty():
		return {"ok": false, "error": "The v4 transaction actor is unavailable."}
	var argv: Array[String] = []
	argv.assign(command.slice(1))
	argv.append_array(arguments)
	var previous := isolate_uv_environment()
	var info := OS.execute_with_pipe(command[0], argv)
	restore_uv_environment(previous)
	if info.is_empty():
		return {"ok": false, "error": "The v4 transaction actor could not be started."}
	var pid := int(info.get("pid", -1))
	var stdout_pipe: Variant = info.get("stdio", null)
	var stderr_pipe: Variant = info.get("stderr", null)
	if pid <= 1:
		_close(stdout_pipe, stderr_pipe)
		return {"ok": false, "error": "The v4 transaction actor could not be started."}
	var deadline := Time.get_ticks_msec() + timeout_msec
	while OS.is_process_running(pid):
		var cancelled := cancel_check.is_valid() and bool(cancel_check.call())
		if cancelled or Time.get_ticks_msec() >= deadline:
			_terminate(pid)
			_close(stdout_pipe, stderr_pipe)
			return {
				"ok": false,
				"error": (
					"Migration preparation was cancelled."
					if cancelled
					else "The v4 transaction actor timed out; restart Godot before retrying."
				),
				"termination_unproven": OS.get_name() != "Windows" or OS.is_process_running(pid),
			}
		OS.delay_msec(POLL_MSEC)
	var stdout := _drain(stdout_pipe)
	var stderr_text := _drain(stderr_pipe)
	_close(stdout_pipe, stderr_pipe)
	if OS.get_process_exit_code(pid) != 0:
		return {"ok": false, "error": _safe_actor_error(stderr_text)}
	return {"ok": true, "stdout": stdout}


static func create_process(command: Array[String], arguments: Array[String]) -> int:
	if command.is_empty():
		return -1
	var argv: Array[String] = []
	argv.assign(command.slice(1))
	argv.append_array(arguments)
	var previous := isolate_uv_environment()
	var pid := OS.create_process(command[0], argv)
	restore_uv_environment(previous)
	return pid


static func isolate_uv_environment() -> Dictionary:
	var previous := {}
	for name in UV_ENVIRONMENT:
		previous[name] = {"present": OS.has_environment(name), "value": OS.get_environment(name)}
		OS.unset_environment(name)
	OS.set_environment("UV_NO_PROGRESS", "1")
	return previous


static func restore_uv_environment(previous: Dictionary) -> void:
	for name in previous:
		if bool(previous[name].present):
			OS.set_environment(name, str(previous[name].value))
		else:
			OS.unset_environment(name)


static func _terminate(pid: int) -> void:
	if OS.get_name() == "Windows":
		OS.execute("taskkill", ["/PID", str(pid), "/T", "/F"], [], true)
	else:
		OS.kill(pid)
	var deadline := Time.get_ticks_msec() + 500
	while OS.is_process_running(pid) and Time.get_ticks_msec() < deadline:
		OS.delay_msec(POLL_MSEC)


static func _drain(pipe: Variant) -> String:
	if not pipe is FileAccess:
		return ""
	var data := PackedByteArray()
	var file := pipe as FileAccess
	while data.size() < MAX_OUTPUT_BYTES:
		var chunk := file.get_buffer(mini(4096, MAX_OUTPUT_BYTES - data.size()))
		if chunk.is_empty():
			break
		data.append_array(chunk)
		if file.eof_reached():
			break
	return data.get_string_from_utf8()


static func _close(stdout_pipe: Variant, stderr_pipe: Variant) -> void:
	if stdout_pipe is FileAccess:
		(stdout_pipe as FileAccess).close()
	if stderr_pipe is FileAccess:
		(stderr_pipe as FileAccess).close()


static func _safe_actor_error(stderr_text: String) -> String:
	for raw_line in stderr_text.split("\n"):
		var line := raw_line.strip_edges()
		if line.begins_with("godot-ai-update-transaction: ") and line.to_utf8_buffer().size() <= 1024:
			return line
	return "The signed v4 transaction actor refused the migration."
