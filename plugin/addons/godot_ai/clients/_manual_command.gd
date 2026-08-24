@tool
class_name McpManualCommand
extends RefCounted

const SHELL_POSIX := "posix"
const SHELL_POWERSHELL := "powershell"
## Keep this intersection deliberately small. PowerShell treats a leading `@`
## as splatting syntax and commas as list separators, while POSIX shells accept
## both literally; quoting either is safer than trying to infer token position.
const _SHELL_BARE_SAFE_CHARS := "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_+=:./-"

## Synthesize the "Run this manually" string the dock surfaces when
## auto-configure can't find a CLI / write a file. Generated from the
## descriptor's declarative fields — there is no per-client builder
## Callable. See `_base.gd` for why descriptors are data-only.


static func build(
	client: McpClient,
	server_name: String,
	server_url: String,
	resolved_path: String,
	launch: Dictionary = {},
) -> String:
	match client.config_type:
		"cli":
			return _build_cli(client, server_name, server_url, resolved_path, launch)
		"json":
			return _build_json(client, server_name, server_url, resolved_path, launch)
		"toml":
			return _build_toml(client, server_name, server_url, resolved_path, launch)
		"yaml":
			return _build_yaml(client, server_name, server_url, resolved_path, launch)
	return ""


## CLI clients: format the register template against the *short* CLI name so
## the user can paste it into a terminal regardless of where their binary
## lives. (The auto-configure path resolves to an absolute uvx-style path;
## that's noise for a paste-into-terminal hint. The attach launcher path
## inside a command-shape line stays absolute — status verification compares
## the registered command against the resolved launcher verbatim.)
static func _build_cli(
	client: McpClient,
	server_name: String,
	server_url: String,
	resolved_path: String = "",
	launch: Dictionary = {},
) -> String:
	if client.cli_register_template.is_empty() or client.cli_names.is_empty():
		return ""
	var shell_kind := _shell_kind_for_platform()
	var short_name: String = String(client.cli_names[0])
	# Prefer the non-.exe form for a cross-platform-looking command line.
	for n in client.cli_names:
		if not String(n).ends_with(".exe"):
			short_name = String(n)
			break
	var cmd := ""
	if client.command_shape != McpClient.CommandShape.NONE:
		var launch_error := McpCliStrategy.command_launch_error(client, launch)
		if not launch_error.is_empty():
			cmd = "Attach launch command unavailable: %s" % launch_error
		else:
			var args := McpCliStrategy.format_args(client.cli_register_template, server_name, server_url, launch)
			var parts: Array[String] = [short_name]
			for arg in args:
				parts.append(String(arg))
			cmd = _format_shell_command(parts, shell_kind)
	else:
		var args := McpCliStrategy.format_args(client.cli_register_template, server_name, server_url)
		var parts: Array[String] = [short_name]
		for arg in args:
			parts.append(String(arg))
		cmd = _format_shell_command(parts, shell_kind)
	## #877: Configure runs more than the line above. For a `{scope}` descriptor
	## it first runs the unregister template once per scope in CLIENT_SCOPES, so
	## pressing Configure at ANY setting — the default `user` included — deletes
	## a `godot-ai` entry from every scope, including one a team keeps by hand in
	## a checked-in `.mcp.json`. Rendering only the register line made this hint
	## disagree with what the button actually does, which is the worst property a
	## "run this manually" string can have.
	var sweep := _scope_sweep_note(client, server_name, server_url, short_name, shell_kind)
	if not sweep.is_empty():
		cmd = "%s\n\n%s" % [cmd, sweep]
	# #463: a CLI client with a JSON fallback (Claude Code) may have no `claude`
	# binary at all — e.g. installed only as a VS Code/Cursor extension. The CLI
	# line above is useless to that user, so also show the config-file edit that
	# auto-configure falls back to writing.
	if client.has_json_fallback() and not resolved_path.is_empty():
		return "%s\n\nNo `%s` CLI (e.g. installed as a VS Code/Cursor extension)? %s" % [
			cmd, short_name, _build_json(client, server_name, server_url, resolved_path, launch),
		]
	return cmd


## Render the pre-cleanup removes Configure runs before registering a `{scope}`
## descriptor. Shares `_shell_display_arg` with `_format_shell_command` but not
## its label — these lines belong under the caller's own heading, and repeating
## "Run in PowerShell:" four times would bury the one line that registers.
##
## Returns "" for descriptors without the token: those keep the single
## implicit-scope pass they always had, which removes exactly the entry the
## register is about to rewrite and so has no side effect worth surfacing.
static func _scope_sweep_note(
	client: McpClient,
	server_name: String,
	server_url: String,
	short_name: String,
	shell_kind: String,
) -> String:
	if client.cli_unregister_template.is_empty():
		return ""
	if not McpCliStrategy.uses_scope_token(client):
		return ""
	var lines: Array[String] = []
	for scope in McpSettings.CLIENT_SCOPES:
		var args := McpCliStrategy.format_args(
			client.cli_unregister_template, server_name, server_url, {}, String(scope)
		)
		var rendered: Array[String] = [_shell_display_arg(short_name, shell_kind)]
		for arg in args:
			rendered.append(_shell_display_arg(String(arg), shell_kind))
		lines.append(" ".join(rendered))
	if lines.is_empty():
		return ""
	return (
		"Configure also runs these first, clearing %s out of every scope. "
		% server_name
		+ "The project-scope line rewrites the .mcp.json in the editor's working "
		+ "directory — which is wherever the editor was launched from, not "
		+ "necessarily this project — so it will drop a hand-maintained %s entry there:\n%s"
		% [server_name, "\n".join(lines)]
	)


static func _shell_kind_for_platform() -> String:
	return SHELL_POWERSHELL if OS.get_name() == "Windows" else SHELL_POSIX


## Render a command for one explicitly named shell. The label is load-bearing:
## POSIX and PowerShell use different escaping for embedded single quotes, so
## presenting the command without its target shell invites a bad copy/paste.
static func _format_shell_command(parts: Array[String], shell_kind: String) -> String:
	var rendered: Array[String] = []
	for part in parts:
		rendered.append(_shell_display_arg(part, shell_kind))
	var label := "Run in PowerShell:" if shell_kind == SHELL_POWERSHELL else "Run in a POSIX shell:"
	return "%s\n%s" % [label, " ".join(rendered)]


## Quote one argv element for the paste-into-terminal hint. Single-quoted
## strings are literal in both supported shells, but embedded single quotes
## have shell-specific spellings. Backslashes, double quotes, dollar signs,
## and PowerShell backticks remain byte-for-byte unchanged inside the quotes.
static func _shell_display_arg(arg: String, shell_kind: String) -> String:
	if arg.is_empty():
		return "''"
	var stays_bare := true
	for index in range(arg.length()):
		if _SHELL_BARE_SAFE_CHARS.find(arg.substr(index, 1)) < 0:
			stays_bare = false
			break
	if stays_bare:
		return arg
	if shell_kind == SHELL_POWERSHELL:
		return "'%s'" % arg.replace("'", "''")
	return "'%s'" % arg.replace("'", "'\"'\"'")


static func _build_json(
	client: McpClient,
	server_name: String,
	server_url: String,
	resolved_path: String,
	launch: Dictionary = {},
) -> String:
	var key := client.server_key_path[0] if client.server_key_path.size() > 0 else "mcpServers"
	if client.command_shape != McpClient.CommandShape.NONE:
		var lines: Array[String] = []
		var launch_error := McpJsonStrategy.command_launch_error(client, launch)
		if launch_error.is_empty():
			var command_entry := McpJsonStrategy.build_entry(client, server_url, null, launch)
			lines.append("Edit %s and add under \"%s\":" % [resolved_path, key])
			lines.append("  \"%s\": %s" % [server_name, _format_entry_inline(command_entry)])
		else:
			lines.append("Attach launch command unavailable: %s" % launch_error)
		if client.command_supports_url_fallback:
			lines.append("")
			lines.append("Advanced fallback — use this URL-mode entry instead; never configure both shapes together. URL mode depends on your client's own reconnect behavior. If the server is down when the client starts, restarting the client may be required.")
			lines.append("Edit %s and add under \"%s\":" % [resolved_path, key])
			var fallback_entry := McpJsonStrategy.build_url_entry(client, server_url)
			lines.append("  \"%s\": %s" % [server_name, _format_entry_inline(fallback_entry)])
		return "\n".join(lines)
	var entry := McpJsonStrategy.build_entry(client, server_url)
	return "Edit %s and add under \"%s\":\n  \"%s\": %s" % [resolved_path, key, server_name, _format_entry_inline(entry)]


static func _build_toml(
	client: McpClient,
	_server_name: String,
	server_url: String,
	resolved_path: String,
	launch: Dictionary = {},
) -> String:
	var header := _toml_header(client)
	if client.command_shape != McpClient.CommandShape.NONE:
		var lines: Array[String] = []
		var rendered := McpTomlStrategy.render_body(client, server_url, launch)
		if bool(rendered.get("ok", false)):
			lines.append("Edit %s and add:" % resolved_path)
			lines.append("  %s" % header)
			for body_line in rendered.get("lines", []):
				lines.append("  %s" % str(body_line))
		else:
			lines.append("Attach launch command unavailable: %s" % str(rendered.get("error", "no compatible launcher found")))
		if client.command_supports_url_fallback:
			lines.append("")
			lines.append("Advanced fallback — replace the command/args block above with this URL-mode block; never configure both shapes together. URL mode depends on your client's own reconnect behavior. If the server is down when the client starts, restarting the client may be required.")
			lines.append("Edit %s and add:" % resolved_path)
			lines.append("  %s" % header)
			lines.append("  url = %s" % McpTomlStrategy.encode_basic_string(server_url))
		return "\n".join(lines)
	var body := McpTomlStrategy.format_body(client.toml_body_template, server_url)
	var lines: Array[String] = ["Edit %s and add:" % resolved_path, "  %s" % header]
	for b in body:
		lines.append("  %s" % String(b))
	return "\n".join(lines)


static func _build_yaml(
	client: McpClient,
	server_name: String,
	server_url: String,
	resolved_path: String,
	launch: Dictionary = {},
) -> String:
	var key := client.server_key_path[0] if client.server_key_path.size() > 0 else "mcp_servers"
	if client.command_shape != McpClient.CommandShape.NONE:
		var lines: Array[String] = []
		var launch_error := McpYamlStrategy.command_launch_error(client, launch)
		if launch_error.is_empty():
			var command_entry := McpYamlStrategy.build_entry(client, server_url, null, launch)
			lines.append("Edit %s and add under '%s':" % [resolved_path, key])
			for entry_line in McpYamlStrategy.render_entry_lines(server_name, command_entry):
				lines.append(String(entry_line))
		else:
			lines.append("Attach launch command unavailable: %s" % launch_error)
		if client.command_supports_url_fallback:
			lines.append("")
			lines.append("Advanced fallback — use this URL-mode entry instead; never configure both shapes together. URL mode depends on your client's own reconnect behavior. If the server is down when the client starts, restarting the client may be required.")
			lines.append("Edit %s and add under '%s':" % [resolved_path, key])
			var fallback_entry := {client.entry_url_field: server_url}
			for entry_line in McpYamlStrategy.render_entry_lines(server_name, fallback_entry):
				lines.append(String(entry_line))
		return "\n".join(lines)
	var entry := McpYamlStrategy.build_entry(client, server_url)
	var lines: Array[String] = [
		"Edit %s and add under '%s':" % [resolved_path, key],
		"  %s:" % server_name,
	]
	for k in entry:
		lines.append("    %s: %s" % [k, str(entry[k])])
	return "\n".join(lines)


## Mirrors the [section."name"] header `_toml_strategy._primary_header`
## emits, kept here so the manual-command text matches the file we'd write.
static func _toml_header(client: McpClient) -> String:
	var parts := client.toml_section_path
	if parts.size() < 2:
		return "[%s]" % ".".join(parts)
	var section := ".".join(McpClient._array_from_packed(McpClient._packed_slice(parts, 0, parts.size() - 1)))
	var name := parts[parts.size() - 1]
	return "[%s.\"%s\"]" % [section, name]


## Format an entry dict as a single inline JSON-ish string, matching the
## pre-refactor manual-command style: `{ "k": v, "k": v }` with spaces.
## Pre-existing manual-command tests assert the exact substring shape; this
## keeps them stable.
##
## Uses `JSON.stringify` for every leaf String (key OR value) so paths
## containing backslashes / quotes / newlines render as syntactically valid
## JSON. A Windows uvx path like `C:\Users\foo\uvx.exe` would otherwise be
## emitted as `"C:\Users\foo\uvx.exe"` — invalid JSON, unsafe to paste.
static func _format_entry_inline(entry: Dictionary) -> String:
	var parts: Array[String] = []
	for k in entry:
		parts.append("%s: %s" % [JSON.stringify(String(k)), _format_value(entry[k])])
	if parts.is_empty():
		return "{}"
	return "{ %s }" % ", ".join(parts)


static func _format_value(value: Variant) -> String:
	# Strings, bools, numbers, null all round-trip correctly through JSON.stringify
	# without spurious quoting of non-string scalars (true → `true`, 5 → `5`).
	# Arrays and Dictionaries are formatted manually so the inline ` { k: v } `
	# spacing matches the pre-refactor manual-command output shape that tests
	# pin with assert_contains.
	if value is Array:
		var arr_parts: Array[String] = []
		for v in value:
			arr_parts.append(_format_value(v))
		return "[%s]" % ", ".join(arr_parts)
	if value is Dictionary:
		var d_parts: Array[String] = []
		for k in value:
			d_parts.append("%s: %s" % [JSON.stringify(String(k)), _format_value(value[k])])
		if d_parts.is_empty():
			return "{}"
		return "{ %s }" % ", ".join(d_parts)
	return JSON.stringify(value)
