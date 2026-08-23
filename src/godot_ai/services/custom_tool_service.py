"""Server-side catalog of plugin-registered custom tools.

The Godot plugin pushes ``custom_tools_changed`` WS events (one full
snapshot per editor session); this service caches them per session and
broadcasts MCP ``notifications/tools/list_changed`` so connected AI
clients re-fetch the tool list.

Broadcast mechanism: FastMCP 3.4.2 has no out-of-request-context
broadcast API — ``Context.send_notification`` requires an active request.
Instead, ``TrackMcpSessions`` middleware (``middleware/track_mcp_sessions``)
registers every live ``mcp.server.session.ServerSession`` here in a
``WeakSet``, and ``notify_tools_change`` calls the SDK's official
``ServerSession.send_tool_list_changed()`` on each. This works uniformly
across stdio / sse / streamable-http.

Do NOT reach into transport internals (e.g. the streamable-http session
manager's ``_server_instances`` / ``_read_stream_writer``): the read
stream is the server's INBOUND channel — writing a notification there
feeds it back into our own dispatcher as a forged client message and the
MCP client never sees it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import weakref
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from mcp.server.session import ServerSession

logger = logging.getLogger(__name__)

## Server-side mirrors of the plugin's register-time budgets
## (mcp_custom_tool_spec.gd MAX_DESCRIPTION_CHARS / MAX_SCHEMA_BYTES).
## The plugin enforces them at register time, but the WS event is the
## trust boundary here: a peer speaking the protocol directly must not be
## able to park megabytes of agent-visible text in the catalog or hold
## memory up to the 4 MB message cap per push.
MAX_TOOLS_PER_SESSION = 128
MAX_NAME_CHARS = 128
MAX_DESCRIPTION_CHARS = 600
MAX_SCHEMA_BYTES = 8192

## Per-session cap on a tools/list_changed send. notify_tools_change is
## awaited inline from the editor WebSocket receive loop and disconnect
## cleanup, so a stalled MCP transport (full stdio pipe, slow
## streamable-http client) must not hang that editor's heartbeats / command
## dispatch indefinitely.
_NOTIFY_TIMEOUT_S = 5.0


class CustomToolDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_CHARS)
    description: str = Field(max_length=MAX_DESCRIPTION_CHARS)
    params_schema: dict | None = None
    source: str | None = Field(default=None, max_length=256)
    deferred: bool | None = None
    timeout_ms: int | None = Field(default=None, ge=0, le=120_000)
    requires_writable: bool | None = None
    undoable: bool | None = None

    @field_validator("params_schema")
    @classmethod
    def _schema_within_budget(cls, value: dict | None) -> dict | None:
        if value is not None and len(json.dumps(value).encode("utf-8")) > MAX_SCHEMA_BYTES:
            raise ValueError(f"params_schema exceeds {MAX_SCHEMA_BYTES} UTF-8 bytes")
        return value


class CustomToolService:
    _instance: CustomToolService | None = None

    def __init__(self):
        CustomToolService._instance = self
        ## godot: session_id -> {tool_name -> definition}. Per-session so a
        ## disconnecting godot editor drops ONLY its own tools (multiple editors
        ## can register custom tools concurrently).
        self._tools_by_session: dict[str, dict[str, CustomToolDefinition]] = {}
        ## agent: Live MCP client sessions, fed by TrackMcpSessions middleware.
        ## WeakSet: a closed session is dropped by GC — we never own its
        ## lifecycle, we only borrow it to send notifications.
        self._mcp_sessions: weakref.WeakSet[ServerSession] = weakref.WeakSet()
        ## Per-send timeout for notify_tools_change (tests shrink it).
        self.notify_timeout_s: float = _NOTIFY_TIMEOUT_S

    @classmethod
    def get_instance(cls):
        """Lazy singleton — constructs on first access.

        server.py's lifespan still constructs one explicitly per run (a
        fresh server must start with an empty catalog); laziness is for
        direct consumers in tests and tooling that never run the lifespan.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # --- MCP session tracking (called from TrackMcpSessions middleware) ---

    def track_mcp_session(self, session: ServerSession) -> None:
        self._mcp_sessions.add(session)

    # --- Tool catalog ---

    def update_session_tools(self, session_id: str, tools: list[CustomToolDefinition]) -> None:
        """Replace the full tool snapshot for one Godot editor session."""
        if tools:
            self._tools_by_session[session_id] = {t.name: t for t in tools}
        else:
            self._tools_by_session.pop(session_id, None)

    def remove_session(self, session_id: str) -> bool:
        """Drop all tools of a disconnected editor session.

        Returns True if the session had tools (caller should broadcast
        list_changed), False otherwise.
        """
        return self._tools_by_session.pop(session_id, None) is not None

    def get_tools(self, session_id: str | None = None) -> list[CustomToolDefinition]:
        """Tools for one Godot editor session, or a merged fallback.

        With ``session_id``: only that session's tools (empty if the
        session is unknown/disconnected). This is the active/pinned view
        ``custom_manage`` advertises as "Active session only" — list and
        invoke must read the SAME session that dispatch routes to,
        otherwise session A's tool can be validated while the call lands
        on session B.

        Without ``session_id``: merged across all sessions (first-seen
        wins on collisions) for diagnostics/admin listings only.
        """
        if session_id is not None:
            return list(self._tools_by_session.get(session_id, {}).values())
        merged: dict[str, CustomToolDefinition] = {}
        for tools in self._tools_by_session.values():
            for name, definition in tools.items():
                merged.setdefault(name, definition)
        return list(merged.values())

    def get_tool(
        self, tool_name: str, session_id: str | None = None
    ) -> CustomToolDefinition | None:
        """Tool lookup by name, optionally scoped to a specific session.

        With session_id: look only in that session so invoke validates
        against the same editor it dispatches to. Without: first-seen
        across sessions (diagnostics fallback).
        """

        if session_id is not None:
            return self._tools_by_session.get(session_id, {}).get(tool_name)
        for tools in self._tools_by_session.values():
            if tool_name in tools:
                return tools[tool_name]
        return None

    # --- Notification broadcast ---

    async def notify_tools_change(self) -> None:
        """Broadcast tools/list_changed to ALL connected MCP clients.

        Concurrent + per-session timeout + exception isolation: a dead or
        stalled MCP transport (full stdio pipe, slow streamable-http client)
        can neither block the other clients nor hang the caller longer than
        ``notify_timeout_s``. This is awaited inline from the editor
        WebSocket receive loop and disconnect cleanup, so bounding it keeps
        a stuck MCP client from stalling that editor's heartbeats / command
        dispatch. ``gather`` returns once every send has completed or
        timed out — fast clients don't wait for the slowest beyond its cap.
        """
        sessions = list(self._mcp_sessions)
        if not sessions:
            return
        await asyncio.gather(
            *(self._notify_one(s) for s in sessions),
            return_exceptions=True,
        )

    async def _notify_one(self, session: ServerSession) -> None:
        try:
            await asyncio.wait_for(
                session.send_tool_list_changed(), timeout=self.notify_timeout_s
            )
        except Exception:
            ## Timeout, transport torn down, or send raised — drop the corpse
            ## so the next broadcast doesn't retry it (WeakSet would GC it
            ## eventually, but not necessarily before then).
            self._mcp_sessions.discard(session)
            logger.debug("Dropped MCP session from list_changed broadcast", exc_info=True)
