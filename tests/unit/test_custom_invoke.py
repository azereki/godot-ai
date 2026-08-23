"""Unit tests for the custom_manage handlers (list/invoke) and the
server-side catalog trust boundary.

``custom_invoke`` is driven against a fake DirectRuntime — the handler
only needs ``active_session_id`` and ``send_command`` — so routing,
timeout forwarding, and the conditional writable gate are pinned without
a live editor. The WS-event tests drive ``_handle_event`` unbound on a
SimpleNamespace stub, same pattern as test_telemetry_integration.
"""

from __future__ import annotations

import asyncio
import types

import pytest
from pydantic import ValidationError

from godot_ai.godot_client.client import GodotCommandError
from godot_ai.handlers import custom as custom_mod
from godot_ai.protocol.envelope import CustomToolsChangedEvent
from godot_ai.services.custom_tool_service import (
    MAX_DESCRIPTION_CHARS,
    MAX_SCHEMA_BYTES,
    CustomToolDefinition,
    CustomToolService,
)


@pytest.fixture(autouse=True)
def fresh_service() -> CustomToolService:
    CustomToolService._instance = None
    return CustomToolService.get_instance()


class _FakeRuntime:
    def __init__(self, session_id: str | None = "s1") -> None:
        self.active_session_id = session_id
        self.sent: list[dict] = []
        self.response: dict = {"status": "ok"}

    async def send_command(self, command, params=None, session_id=None, timeout=5.0):
        self.sent.append(
            {
                "command": command,
                "params": params,
                "session_id": session_id,
                "timeout": timeout,
            }
        )
        return self.response


def _register(service: CustomToolService, session_id: str, **extra) -> CustomToolDefinition:
    tool = CustomToolDefinition(name="my_tool", description="d", **extra)
    service.update_session_tools(session_id, [tool])
    return tool


# --- custom_invoke routing ---


def test_invoke_routes_with_prefix_params_and_session(fresh_service) -> None:
    _register(fresh_service, "s1")
    runtime = _FakeRuntime("s1")
    result = asyncio.run(custom_mod.custom_invoke(runtime, "my_tool", {"a": 1}))
    assert result == {"status": "ok"}
    assert len(runtime.sent) == 1
    call = runtime.sent[0]
    assert call["command"] == "custom_tool:my_tool"
    assert call["params"] == {"a": 1}
    assert call["session_id"] == "s1"


def test_invoke_unknown_tool_raises(fresh_service) -> None:
    runtime = _FakeRuntime("s1")
    with pytest.raises(GodotCommandError):
        asyncio.run(custom_mod.custom_invoke(runtime, "nope"))
    assert runtime.sent == []


def test_invoke_no_active_session_raises_without_merged_fallback(fresh_service) -> None:
    ## The tool exists in SOME session, but with no active session the
    ## invoke must fail rather than validate against a session dispatch
    ## can't reach (session-confusion guard).
    _register(fresh_service, "s1")
    runtime = _FakeRuntime(None)
    with pytest.raises(GodotCommandError):
        asyncio.run(custom_mod.custom_invoke(runtime, "my_tool"))
    assert runtime.sent == []


def test_invoke_timeout_follows_definition(fresh_service) -> None:
    _register(fresh_service, "s1", timeout_ms=90_000)
    runtime = _FakeRuntime("s1")
    asyncio.run(custom_mod.custom_invoke(runtime, "my_tool"))
    ## Plugin-side deferred budget 90s + transport margin — NOT the 5s
    ## send_command default, which would fail every slow custom tool.
    assert runtime.sent[0]["timeout"] == pytest.approx(92.0)


def test_invoke_timeout_defaults_when_unset(fresh_service) -> None:
    _register(fresh_service, "s1", timeout_ms=None)
    runtime = _FakeRuntime("s1")
    asyncio.run(custom_mod.custom_invoke(runtime, "my_tool"))
    assert runtime.sent[0]["timeout"] == pytest.approx(6.5)


# --- conditional writable gate ---


def _patch_writable(monkeypatch) -> list:
    calls: list = []

    async def _fake_gate(runtime):
        calls.append(runtime)

    monkeypatch.setattr(custom_mod, "require_writable_async", _fake_gate)
    return calls


def test_invoke_gates_write_tools(fresh_service, monkeypatch) -> None:
    calls = _patch_writable(monkeypatch)
    _register(fresh_service, "s1", requires_writable=True)
    runtime = _FakeRuntime("s1")
    asyncio.run(custom_mod.custom_invoke(runtime, "my_tool"))
    assert len(calls) == 1


def test_invoke_does_not_gate_read_tools(fresh_service, monkeypatch) -> None:
    ## requires_writable=false → "reads run any time" per the spec contract
    ## (mcp_custom_tool_spec.gd); the plugin wrapper is the enforcement
    ## point for gated tools, mirrored here.
    calls = _patch_writable(monkeypatch)
    _register(fresh_service, "s1", requires_writable=False)
    runtime = _FakeRuntime("s1")
    asyncio.run(custom_mod.custom_invoke(runtime, "my_tool"))
    assert calls == []


# --- custom_list ---


def test_list_empty_without_active_session(fresh_service) -> None:
    _register(fresh_service, "s1")
    runtime = _FakeRuntime(None)
    result = asyncio.run(custom_mod.custom_list(runtime))
    ## No merged cross-session leak: another editor's tools must not be
    ## advertised when invoke has no dispatch target.
    assert result["tool_count"] == 0
    assert result["tools"] == []


def test_list_scoped_to_active_session(fresh_service) -> None:
    _register(fresh_service, "s1")
    fresh_service.update_session_tools(
        "s2", [CustomToolDefinition(name="other", description="d")]
    )
    runtime = _FakeRuntime("s1")
    result = asyncio.run(custom_mod.custom_list(runtime))
    assert [t["name"] for t in result["tools"]] == ["my_tool"]


# --- server-side catalog budgets (WS trust boundary) ---


def test_definition_rejects_oversized_description() -> None:
    with pytest.raises(ValidationError):
        CustomToolDefinition(name="t", description="x" * (MAX_DESCRIPTION_CHARS + 1))


def test_definition_rejects_oversized_schema_utf8_bytes() -> None:
    ## Multi-byte chars: the budget is UTF-8 bytes, not Python chars.
    payload = {"desc": "é" * (MAX_SCHEMA_BYTES // 2)}
    with pytest.raises(ValidationError):
        CustomToolDefinition(name="t", description="d", params_schema=payload)


def test_definition_rejects_empty_name_and_wild_timeout() -> None:
    with pytest.raises(ValidationError):
        CustomToolDefinition(name="", description="d")
    with pytest.raises(ValidationError):
        CustomToolDefinition(name="t", description="d", timeout_ms=10_000_000)


def test_event_rejects_unbounded_tool_count() -> None:
    with pytest.raises(ValidationError):
        CustomToolsChangedEvent(tools=[{"name": f"t{i}"} for i in range(129)])
    ## And a missing tools list is malformed, not "empty".
    with pytest.raises(ValidationError):
        CustomToolsChangedEvent()


# --- token gate on custom_tools_changed ---


def _event_stub(auth_token: str | None, token_authenticated: bool, service):
    from godot_ai.sessions.registry import Session, SessionRegistry

    registry = SessionRegistry()
    session = Session(
        session_id="demo@a3f2",
        godot_version="4.4.1",
        project_path="/tmp/demo",
        plugin_version="0.0.1",
        token_authenticated=token_authenticated,
    )
    registry.register(session)
    return types.SimpleNamespace(
        registry=registry,
        _auth_token=auth_token,
        _custom_tool_service=service,
    )


def _push_tools(stub) -> None:
    from godot_ai.transport.websocket import GodotWebSocketServer

    asyncio.run(
        GodotWebSocketServer._handle_event(
            stub,
            "demo@a3f2",
            {
                "event": "custom_tools_changed",
                "data": {"tools": [{"name": "t", "description": "d"}]},
            },
        )
    )


def test_tokened_launch_drops_unauthenticated_catalog_push(fresh_service) -> None:
    stub = _event_stub("secret", token_authenticated=False, service=fresh_service)
    _push_tools(stub)
    assert fresh_service.get_tools(session_id="demo@a3f2") == []


def test_tokened_launch_accepts_authenticated_catalog_push(fresh_service) -> None:
    stub = _event_stub("secret", token_authenticated=True, service=fresh_service)
    _push_tools(stub)
    assert [t.name for t in fresh_service.get_tools(session_id="demo@a3f2")] == ["t"]


def test_tokenless_launch_accepts_catalog_push(fresh_service) -> None:
    ## Compat identity model unchanged: no token configured → any local
    ## session may publish (budgets still bound the payload).
    stub = _event_stub(None, token_authenticated=False, service=fresh_service)
    _push_tools(stub)
    assert [t.name for t in fresh_service.get_tools(session_id="demo@a3f2")] == ["t"]
