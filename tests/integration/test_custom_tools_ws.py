"""Integration tests: custom_tools_changed WS events → CustomToolService.

Two layers:
  * WS event handling — a mock Godot plugin pushes tool snapshots over the
    real WebSocket; the server must parse, store, and clear them per
    session, including on disconnect.
  * End-to-end — plugin pushes tools, an MCP client sees them via the
    ``custom_manage(op="list")`` tool (the full plugin → service → FastMCP
    → client chain).

Catalog isolation: CustomToolService is a process-level singleton, so the
WS-event suite clears its catalog before each test — a leftover tool from
a previous test would otherwise leak in and flake assertions.
"""

from __future__ import annotations

import asyncio

import pytest


def _tool_payload(name: str = "gdunit_run", **extra) -> dict:
    base = {
        "name": name,
        "description": f"run {name}",
        "params_schema": {"type": "object"},
        "source": "gdunit4_mcp",
    }
    base.update(extra)
    return base


@pytest.fixture(autouse=True)
def _isolate_catalog():
    """CustomToolService is a process singleton — wipe between tests."""
    from godot_ai.services.custom_tool_service import CustomToolService

    svc = CustomToolService.get_instance()
    svc._tools_by_session.clear()
    yield
    svc._tools_by_session.clear()


class TestCustomToolsWsEvents:
    """Plugin pushes custom_tools_changed → server catalog updates."""

    async def test_event_populates_catalog(self, harness):
        plugin = await harness.connect_plugin(session_id="s-ct-1")
        try:
            await plugin.send_event(
                "custom_tools_changed",
                {"tools": [_tool_payload("t1"), _tool_payload("t2")]},
            )
            await asyncio.sleep(0.05)
            svc = harness.server._custom_tool_service
            assert {t.name for t in svc.get_tools()} == {"t1", "t2"}
            assert svc.get_tool("t1") is not None
        finally:
            await plugin.close()

    async def test_empty_tools_list_clears_session(self, harness):
        plugin = await harness.connect_plugin(session_id="s-ct-2")
        try:
            await plugin.send_event(
                "custom_tools_changed", {"tools": [_tool_payload("t1")]}
            )
            await asyncio.sleep(0.05)
            assert harness.server._custom_tool_service.get_tool("t1") is not None
            ## Empty snapshot = "I have no tools now", not "ignore this".
            await plugin.send_event("custom_tools_changed", {"tools": []})
            await asyncio.sleep(0.05)
            assert harness.server._custom_tool_service.get_tools() == []
        finally:
            await plugin.close()

    async def test_malformed_tool_definition_dropped(self, harness):
        plugin = await harness.connect_plugin(session_id="s-ct-3")
        try:
            ## Missing required `name` — Pydantic ValidationError must be
            ## caught and the catalog left untouched.
            await plugin.send_event(
                "custom_tools_changed",
                {"tools": [{"description": "no name"}]},
            )
            await asyncio.sleep(0.05)
            assert harness.server._custom_tool_service.get_tools() == []
        finally:
            await plugin.close()

    async def test_disconnect_drops_session_tools(self, harness):
        plugin = await harness.connect_plugin(session_id="s-ct-4")
        await plugin.send_event(
            "custom_tools_changed", {"tools": [_tool_payload("only-here")]}
        )
        await asyncio.sleep(0.05)
        assert harness.server._custom_tool_service.get_tool("only-here") is not None
        await plugin.close()
        await asyncio.sleep(0.15)  # let server process the disconnect
        assert harness.server._custom_tool_service.get_tool("only-here") is None

    async def test_two_sessions_merge_catalog(self, harness):
        p1 = await harness.connect_plugin(session_id="s-ct-5a")
        p2 = await harness.connect_plugin(session_id="s-ct-5b")
        try:
            await p1.send_event(
                "custom_tools_changed", {"tools": [_tool_payload("from-a")]}
            )
            await p2.send_event(
                "custom_tools_changed", {"tools": [_tool_payload("from-b")]}
            )
            await asyncio.sleep(0.05)
            names = {
                t.name for t in harness.server._custom_tool_service.get_tools()
            }
            assert names == {"from-a", "from-b"}
        finally:
            await p1.close()
            await p2.close()

    async def test_two_sessions_scoped_catalog(self, harness):
        ## "Active session only": a scoped query returns only the owning
        ## session's tools, so list and invoke stay bound to one editor.
        p1 = await harness.connect_plugin(session_id="s-ct-5c")
        p2 = await harness.connect_plugin(session_id="s-ct-5d")
        try:
            await p1.send_event(
                "custom_tools_changed", {"tools": [_tool_payload("from-c")]}
            )
            await p2.send_event(
                "custom_tools_changed", {"tools": [_tool_payload("from-d")]}
            )
            await asyncio.sleep(0.05)
            svc = harness.server._custom_tool_service
            assert {t.name for t in svc.get_tools(session_id="s-ct-5c")} == {"from-c"}
            assert {t.name for t in svc.get_tools(session_id="s-ct-5d")} == {"from-d"}
            ## A tool that exists in one session must not resolve in the other.
            assert svc.get_tool("from-c", session_id="s-ct-5d") is None
        finally:
            await p1.close()
            await p2.close()

    async def test_payload_unwraps_tools_key_not_dict_keys(self, harness):
        ## Regression guard: an earlier version iterated event_data itself
        ## (yielding the dict KEY "tools" as a string) instead of
        ## event_data["tools"]. A string fed to model_validate must be
        ## rejected without corrupting the catalog.
        plugin = await harness.connect_plugin(session_id="s-ct-6")
        try:
            await plugin.send_event(
                "custom_tools_changed",
                {"tools": [_tool_payload("good")]},
            )
            await asyncio.sleep(0.05)
            assert harness.server._custom_tool_service.get_tool("good") is not None
        finally:
            await plugin.close()


class TestCustomManageEndToEnd:
    """Plugin pushes tools → MCP client lists them via custom_manage(list)."""

    async def test_custom_manage_lists_registered_tools(self, mcp_stack):
        client, plugin = mcp_stack
        await plugin.send_event(
            "custom_tools_changed",
            {
                "tools": [
                    _tool_payload(
                        "e2e_tool",
                        deferred=True,
                        timeout_ms=5000,
                        requires_writable=True,
                    )
                ]
            },
        )
        await asyncio.sleep(0.1)  # let the WS event land in the catalog
        result = await client.call_tool(
            "custom_manage", {"op": "list", "params": {}}
        )
        data = result.structured_content
        assert data["tool_count"] == 1
        tool = data["tools"][0]
        assert tool["name"] == "e2e_tool"
        ## The medium-priority payload fields (#781 comment) round-trip
        ## through the WS event → Pydantic model → MCP tool response.
        assert tool["deferred"] is True
        assert tool["timeout_ms"] == 5000
        assert tool["requires_writable"] is True

    async def test_custom_manage_empty_when_no_tools_pushed(self, mcp_stack):
        client, plugin = mcp_stack
        result = await client.call_tool(
            "custom_manage", {"op": "list", "params": {}}
        )
        data = result.structured_content
        assert data["tool_count"] == 0
        assert data["tools"] == []
