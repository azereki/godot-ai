@tool
extends RefCounted

## bridge between dispatcher and addon handler

const ErrorCodes := preload("res://addons/godot_ai/utils/error_codes.gd")

var _spec: McpCustomToolSpec
var _locator: McpServiceLocator
var _handler_instance = null  # lazily loaded from _spec.script_path

func _init(spec: McpCustomToolSpec, locator: McpServiceLocator) -> void:
	_spec = spec
	_locator = locator

## Invoked by dispatcher._call_handler as .call(params) — SINGLE ARG.
## Internally splits into (clean_params, ctx) for the addon handler.
func invoke(params: Dictionary) -> Dictionary:
	if _handler_instance == null:
		var script := load(_spec.script_path) as GDScript
		if script == null:
			return ErrorCodes.make(ErrorCodes.INTERNAL_ERROR, "Cannot load %s" % _spec.script_path)
		_handler_instance = script.new()  # no-arg; deps via ctx.locator
	## Extract _request_id (dispatcher injected it) and strip from params
	## so the addon sees clean params matching its declared schema (https://github.com/hi-godot/godot-ai/issues/781#issuecomment-5036376599 #2).
	var request_id: String= params.get("_request_id", "")
	var clean_params := params.duplicate()
	clean_params.erase("_request_id")
	## Construct ctx with transport metadata + live-object locator.
	var ctx := McpCallContext.new()
	ctx.request_id = request_id
	ctx.session_id = _locator.get_connection().get_session_id()
	ctx.spec = _spec
	ctx.locator = _locator
	ctx.deadline_msec = Time.get_ticks_msec() + _spec.timeout_ms
	## Readiness gate (https://github.com/hi-godot/godot-ai/issues/781#issuecomment-5036376599 #1): block writes during play/import.
	var _readiness := McpConnection.get_readiness()
	if _spec.requires_writable and (_readiness == "importing" or _readiness == "playing"):
		return ErrorCodes.make(ErrorCodes.EDITOR_NOT_READY, "Editor is '%s' — write blocked for custom tool '%s'" % [_readiness, _spec.name])
	var result: Dictionary = _handler_instance.call(_spec.method, clean_params, ctx)
	if result.get("_deferred", false) and _spec.timeout_ms > 0:
		result["_deferred_timeout_ms"] = _spec.timeout_ms
	return result
