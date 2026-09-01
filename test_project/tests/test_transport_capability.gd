@tool
extends McpTestSuite

const HTTP := "hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh"
const WEBSOCKET := "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
const NONCE := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

var _scratch_dir: String
var _record_path: String


func suite_name() -> String:
	return "transport_capability"


func suite_setup(_ctx: Dictionary) -> void:
	_scratch_dir = OS.get_user_data_dir().path_join("transport_capability_tests")
	DirAccess.make_dir_recursive_absolute(_scratch_dir)
	_record_path = _scratch_dir.path_join("http-8122.json")
	if OS.get_name() != "Windows":
		FileAccess.set_unix_permissions(
			_scratch_dir,
			FileAccess.UNIX_READ_OWNER
			| FileAccess.UNIX_WRITE_OWNER
			| FileAccess.UNIX_EXECUTE_OWNER,
		)


func suite_teardown() -> void:
	DirAccess.remove_absolute(_record_path)
	DirAccess.remove_absolute(_scratch_dir)


func test_reads_exact_private_record() -> void:
	_write(_canonical_record())
	var result := McpTransportCapability._read_path(_record_path)
	assert_eq(result.get("http", ""), HTTP)
	assert_eq(result.get("websocket", ""), WEBSOCKET)
	assert_eq(result.get("instance_nonce", ""), NONCE)


func test_only_canonical_sticky_temp_root_may_be_a_writable_ancestor() -> void:
	var writable := (
		FileAccess.UNIX_READ_OWNER
		| FileAccess.UNIX_WRITE_OWNER
		| FileAccess.UNIX_EXECUTE_OWNER
		| FileAccess.UNIX_READ_GROUP
		| FileAccess.UNIX_WRITE_GROUP
		| FileAccess.UNIX_EXECUTE_GROUP
		| FileAccess.UNIX_READ_OTHER
		| FileAccess.UNIX_WRITE_OTHER
		| FileAccess.UNIX_EXECUTE_OTHER
	)
	var sticky := writable | FileAccess.UNIX_RESTRICTED_DELETE
	assert_true(McpTransportCapability._safe_posix_ancestor_mode("/tmp", sticky))
	assert_true(McpTransportCapability._safe_posix_ancestor_mode("/private/tmp", sticky))
	assert_false(McpTransportCapability._safe_posix_ancestor_mode("/tmp", writable))
	assert_false(McpTransportCapability._safe_posix_ancestor_mode("/untrusted", sticky))


func test_rejects_ambiguous_or_partial_records() -> void:
	var invalid: Array[String] = [
		'{"version":1,"http":"%s","websocket":"%s"}' % [HTTP, WEBSOCKET],
		_canonical_record().replace('"version":1', '"version":1,"version":1'),
		_canonical_record().replace('"version":1', '"version":true'),
		_canonical_record().replace(WEBSOCKET, HTTP),
		_canonical_record().replace(NONCE, "not-hex"),
		_canonical_record().trim_suffix("}") + ',"extra":1}',
	]
	for raw in invalid:
		_write(raw)
		assert_true(
			McpTransportCapability._read_path(_record_path).is_empty(),
			"must reject %s" % raw,
		)


func test_rejects_non_ascii_and_oversize_records() -> void:
	for raw in ["café", "x".repeat(McpTransportCapability.MAX_RECORD_BYTES + 2)]:
		_write(raw)
		assert_true(McpTransportCapability._read_path(_record_path).is_empty())


func test_rejects_permissive_posix_mode() -> void:
	if OS.get_name() == "Windows":
		skip("POSIX modes are unavailable on Windows")
		return
	_write(_canonical_record())
	FileAccess.set_unix_permissions(
		_record_path,
		FileAccess.UNIX_READ_OWNER
		| FileAccess.UNIX_WRITE_OWNER
		| FileAccess.UNIX_READ_GROUP
		| FileAccess.UNIX_READ_OTHER,
	)
	assert_true(McpTransportCapability._read_path(_record_path).is_empty())


func test_rejects_symlinked_ancestor_on_posix() -> void:
	if OS.get_name() == "Windows":
		skip("creating POSIX symlinks is not portable on Windows")
		return
	var real_dir := _scratch_dir + "_real"
	var linked_dir := _scratch_dir + "_link"
	DirAccess.make_dir_recursive_absolute(real_dir)
	FileAccess.set_unix_permissions(
		real_dir,
		FileAccess.UNIX_READ_OWNER
		| FileAccess.UNIX_WRITE_OWNER
		| FileAccess.UNIX_EXECUTE_OWNER,
	)
	var real_record := real_dir.path_join("http-8122.json")
	var file := FileAccess.open(real_record, FileAccess.WRITE)
	file.store_string(_canonical_record())
	file.close()
	FileAccess.set_unix_permissions(
		real_record, FileAccess.UNIX_READ_OWNER | FileAccess.UNIX_WRITE_OWNER
	)
	DirAccess.remove_absolute(linked_dir)
	var rc := OS.execute("ln", ["-s", real_dir, linked_dir])
	if rc != 0:
		skip("could not create a POSIX symlink")
	else:
		assert_true(
			McpTransportCapability._read_path(
				linked_dir.path_join("http-8122.json")
			).is_empty(),
			"an otherwise-private record below a symlinked ancestor must fail closed",
		)
	DirAccess.remove_absolute(linked_dir)
	DirAccess.remove_absolute(real_record)
	DirAccess.remove_absolute(real_dir)


func test_rejects_world_writable_posix_ancestor() -> void:
	if OS.get_name() == "Windows":
		skip("POSIX ancestor modes are unavailable on Windows")
		return
	var unsafe_dir := _scratch_dir + "_unsafe"
	var private_dir := unsafe_dir.path_join("private")
	var unsafe_record := private_dir.path_join("http-8122.json")
	DirAccess.make_dir_recursive_absolute(private_dir)
	FileAccess.set_unix_permissions(
		private_dir,
		FileAccess.UNIX_READ_OWNER
		| FileAccess.UNIX_WRITE_OWNER
		| FileAccess.UNIX_EXECUTE_OWNER,
	)
	FileAccess.set_unix_permissions(
		unsafe_dir,
		FileAccess.UNIX_READ_OWNER
		| FileAccess.UNIX_WRITE_OWNER
		| FileAccess.UNIX_EXECUTE_OWNER
		| FileAccess.UNIX_READ_GROUP
		| FileAccess.UNIX_WRITE_GROUP
		| FileAccess.UNIX_EXECUTE_GROUP
		| FileAccess.UNIX_READ_OTHER
		| FileAccess.UNIX_WRITE_OTHER
		| FileAccess.UNIX_EXECUTE_OTHER,
	)
	var file := FileAccess.open(unsafe_record, FileAccess.WRITE)
	file.store_string(_canonical_record())
	file.close()
	FileAccess.set_unix_permissions(
		unsafe_record, FileAccess.UNIX_READ_OWNER | FileAccess.UNIX_WRITE_OWNER
	)
	assert_true(
		McpTransportCapability._read_path(unsafe_record).is_empty(),
		"a private leaf below a writable ancestor must fail closed",
	)
	## Restore owner-only access before cleanup so the test never leaves a
	## permissive directory behind if the platform enforces deletion modes.
	FileAccess.set_unix_permissions(
		unsafe_dir,
		FileAccess.UNIX_READ_OWNER
		| FileAccess.UNIX_WRITE_OWNER
		| FileAccess.UNIX_EXECUTE_OWNER,
	)
	DirAccess.remove_absolute(unsafe_record)
	DirAccess.remove_absolute(private_dir)
	DirAccess.remove_absolute(unsafe_dir)


func test_windows_rejects_capability_directory_override() -> void:
	var before := OS.get_environment(McpTransportCapability.CAPABILITY_DIR_ENV)
	OS.set_environment(McpTransportCapability.CAPABILITY_DIR_ENV, _scratch_dir)
	var path := McpTransportCapability.path_for_http_port(8122)
	if before.is_empty():
		OS.unset_environment(McpTransportCapability.CAPABILITY_DIR_ENV)
	else:
		OS.set_environment(McpTransportCapability.CAPABILITY_DIR_ENV, before)
	if OS.get_name() == "Windows":
		assert_eq(path, "")
	else:
		assert_eq(path, _record_path)


func test_posix_rejects_relative_capability_directory_override() -> void:
	if OS.get_name() == "Windows":
		skip("Windows rejects every capability-directory override")
		return
	var before := OS.get_environment(McpTransportCapability.CAPABILITY_DIR_ENV)
	OS.set_environment(McpTransportCapability.CAPABILITY_DIR_ENV, "relative/capabilities")
	var path := McpTransportCapability.path_for_http_port(8122)
	if before.is_empty():
		OS.unset_environment(McpTransportCapability.CAPABILITY_DIR_ENV)
	else:
		OS.set_environment(McpTransportCapability.CAPABILITY_DIR_ENV, before)
	assert_eq(path, "")


func test_linux_rejects_relative_xdg_capability_directory() -> void:
	if OS.get_name() != "Linux":
		skip("XDG_CONFIG_HOME selects the capability directory only on Linux")
		return
	var before_override := OS.get_environment(McpTransportCapability.CAPABILITY_DIR_ENV)
	var before_xdg := OS.get_environment("XDG_CONFIG_HOME")
	OS.unset_environment(McpTransportCapability.CAPABILITY_DIR_ENV)
	OS.set_environment("XDG_CONFIG_HOME", "relative/config")
	var path := McpTransportCapability.path_for_http_port(8122)
	if before_override.is_empty():
		OS.unset_environment(McpTransportCapability.CAPABILITY_DIR_ENV)
	else:
		OS.set_environment(McpTransportCapability.CAPABILITY_DIR_ENV, before_override)
	if before_xdg.is_empty():
		OS.unset_environment("XDG_CONFIG_HOME")
	else:
		OS.set_environment("XDG_CONFIG_HOME", before_xdg)
	assert_eq(path, "")


func _write(raw: String) -> void:
	var file := FileAccess.open(_record_path, FileAccess.WRITE)
	file.store_string(raw)
	file.close()
	if OS.get_name() != "Windows":
		FileAccess.set_unix_permissions(
			_record_path,
			FileAccess.UNIX_READ_OWNER | FileAccess.UNIX_WRITE_OWNER,
		)


func _canonical_record() -> String:
	return (
		'{"version":1,"http":"%s","websocket":"%s","instance_nonce":"%s"}'
		% [HTTP, WEBSOCKET, NONCE]
	)
