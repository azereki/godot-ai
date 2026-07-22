from godot_ai.godot_client.client import GodotCommandError
from godot_ai.handlers._readiness import require_writable_async
from godot_ai.runtime.direct import DirectRuntime
from godot_ai.services.custom_tool_service import CustomToolService


async def custom_list(runtime: DirectRuntime) -> dict:
    service = CustomToolService.get_instance()
    ## "Active session only": list the tools of the editor this call will
    ## dispatch to, so the catalog matches what invoke can actually reach.
    tools = service.get_tools(session_id=runtime.active_session_id)
    return {
        "tool_count": len(tools),
        "tools": [t.model_dump() for t in tools],
    }


async def custom_invoke(
    runtime: DirectRuntime,
    tool_name: str,
    params: dict | None = None,
) -> dict:
    service = CustomToolService.get_instance()
    ## Resolve the dispatch target ONCE and use it for both lookup and
    ## send_command, so the definition we validate against belongs to the
    ## same editor we route to (active session, or per-call pin).
    session_id = runtime.active_session_id
    definition = service.get_tool(tool_name, session_id=session_id)
    if definition is None:
        raise GodotCommandError(
            code="UNKNOWN_COMMAND",
            message=f"Custom tool '{tool_name}' not found in session {session_id or '<active>'}",
        )
    await require_writable_async(runtime)
    # Route to plugin as "custom_tool:<name>"
    return await runtime.send_command(
        f"custom_tool:{tool_name}",
        params=params or {},
        session_id=session_id,
    )
