# Port 8000 is in use by another process

Godot AI's local Python backend listens on HTTP port `8000`; its authenticated
editor WebSocket listens on `9500`. Port `8000` is also a common default for
Django, `python -m http.server`, and other development servers.

When a foreign process owns either port, Godot AI does not kill or reuse it.
The dock reports the conflict and suggests free replacements, for example:

> Port 8000 is occupied by an incompatible server. Port 8001 is free — set
> `godot_ai/http_port` in Editor Settings, then reconfigure your clients.

This guide covers that foreign-process case. If the dock identifies a stale
Godot AI process that it can prove belongs to the same local account, use the
dock's recovery action instead.

## 1. Choose free ports

The plugin needs both an HTTP port and a WebSocket port. The conflict message
suggests values checked by the plugin (for example `8001` and `9501`). On
Windows the check also excludes Hyper-V, WSL2, and Docker reserved ranges.

Move only the occupied port if the other one is free. Moving both is often
simpler when another tool owns the same pair.

## 2. Change the Editor Settings

1. Open **Editor → Editor Settings**.
2. Set `godot_ai/http_port` to the chosen HTTP port.
3. Set `godot_ai/ws_port` to the chosen WebSocket port.
4. Reload the plugin from **Project → Project Settings → Plugins**, or restart
   the editor.

These are Editor Settings, not Project Settings. They apply to every project
opened by that Godot editor installation.

## 3. Reconfigure every MCP client

V4 clients do not persist a backend URL or bearer token. Every supported
client launches the `godot-ai attach` stdio bridge, which obtains and rotates
private local capabilities at runtime. The generated command still includes
both port numbers, so a port change requires regeneration.

In the dock, click **Configure** for each client (or **Configure all**). This
rewrites the existing entry with the current exact package version, HTTP and
WebSocket ports, excluded domains, and telemetry preference.

If you maintain an attach entry by hand, change the values after `--port` and
`--ws-port`. Its relevant argv should look like:

```text
godot-ai attach --port 8001 --ws-port 9501
```

Do not replace it with `http://127.0.0.1:8001/mcp`. A persistent bare URL
cannot carry the rotating private capability and is rejected by v4.

## Reverting

After the foreign process is gone, set `godot_ai/http_port` back to `8000` and
`godot_ai/ws_port` back to `9500` (or clear the overrides), reload the plugin,
and run **Configure all** again.
