@tool
class_name McpCallContext
extends RefCounted

var request_id: String = ""
var session_id: String = ""
var deadline_msec: int = 0
var spec: McpCustomToolSpec = null
var locator: McpServiceLocator = null

func is_expired() -> bool:
	if deadline_msec == 0:
		return false
	return Time.get_ticks_msec() > deadline_msec

func send_deferred(payload: Dictionary) -> void:
	if locator == null:
		push_error("McpCallContext: cannot send deferred response, locator is null")
		return
	var conn := locator.get_connection()
	if conn == null:
		push_error("McpCallContext: cannot send deferred response, connection is null")
		return
	conn.send_deferred_response(request_id, payload)
