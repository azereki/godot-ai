<p align="center">
  <img src="docs/hero.png" alt="Godot AI — The wait is over" width="700">
</p>

# Godot AI

[![CI](https://github.com/hi-godot/godot-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/hi-godot/godot-ai/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/hi-godot/godot-ai/graph/badge.svg)](https://codecov.io/gh/hi-godot/godot-ai)
[![Discord](https://img.shields.io/badge/Discord-Join%20chat-5865F2?logo=discord&logoColor=white)](https://discord.gg/FDZ5fr2QkP)

**Godot AI connects Claude Code, Claude Desktop, Codex, Hermes Agent, and other
[MCP](https://modelcontextprotocol.io/introduction) clients to a live Godot
editor.** Its [46 tools and 120+ operations](docs/TOOLS.md) let AI assistants
build scenes, edit nodes and scripts, wire signals, and configure UI, materials,
animation, particles, cameras, and environments.

> 📦 This branch is the unpublished Godot AI v4 candidate. V4 requires Godot
> 4.7+ within the 4.x line; its publication workflow remains closed while the exact candidate and
> independent release trust anchor are qualified. Public marketplace listings
> remain on v3. Do not replace a v3 install yet; see the
> [v4 migration guide](docs/v4-migration.md) for the release gate and eventual
> clean-migration procedure.

> 💬 **[Join the Discord](https://discord.gg/FDZ5fr2QkP)** — questions, showcases, and contributor chat.

---

<p align="center">
  <img src="docs/images/huddemo.gif" alt="Cyberpunk HUD demo" width="800"><br>
  <em>UI demo built in ~2 hours with zero coding, zero image gen, all programmatically drawn by Godot AI — <a href="https://github.com/hi-godot/cyberpunk-hud-demo">source</a></em>
</p>

---

## Quick Start

### Prerequisites

- Godot `4.7+` within the 4.x line
- [uv](https://docs.astral.sh/uv/) (for the Python server)

  <details>
  <summary>How to install uv (macOS / Linux / Windows / package managers)</summary>

  - **macOS / Linux:** `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - **Windows (PowerShell):** `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - **Package managers:** `brew install uv`, `sudo pacman -S uv`,
    `sudo apt install uv`, or `sudo dnf install uv`
  - More options: [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/)

  </details>
- An MCP client ([Claude Code](https://docs.anthropic.com/en/docs/claude-code) | [Codex](https://openai.com/index/codex/) | [Antigravity](https://www.antigravity.dev/))

### 1. Install the plugin

No public v4 install is available while publication is closed. After the
independent release attestation named in the
[migration guide](docs/v4-migration.md) exists, a fresh project will verify the
three v4 assets and extract the verified `godot-ai-v4-plugin.zip` into an absent
`addons/godot_ai` path.

For contributor/dev checkouts only:

```bash
git clone https://github.com/hi-godot/godot-ai.git
mkdir -p your-project/addons   # without this, cp makes addons/ a copy of godot_ai
cp -r godot-ai/plugin/addons/godot_ai your-project/addons/
```

If the project already has Godot AI v3, do not copy or extract over it. Follow
the closed-editor migration procedure, which retains the complete old tree
outside the project before activating v4.

### 2. Enable the plugin

In Godot: **Project > Project Settings > Plugins** — enable **Godot AI**.

The plugin will automatically start the MCP server, connect over WebSocket, and show status in the **Godot AI** dock.

> **Not listed under Plugins?** Godot scans each subdirectory of `res://addons/`
> for a `plugin.cfg`. Check that your project has `addons/godot_ai/plugin.cfg`
> and not `addons/plugin.cfg` — the latter means the plugin contents were copied
> one directory too high.

<p align="center"><img src="docs/images/dock.png" alt="Godot AI dock — Clients & Tools button highlighted" width="350"></p>

### 3. Connect your MCP client

The dock shows every supported client with **Configure** / **Remove** controls;
use **Configure all** to set up every detected client. Supported clients include:

- **Claude Code**, **Claude Desktop**, **Antigravity**, **Hermes Agent**, **DeepSeek Harness**

<details>
<summary><strong>…and 17+ more clients</strong></summary>

Codex, **Grok Build**, Cursor, Devin Desktop, VS Code, VS Code Insiders, Zed,
Gemini CLI, Cline, Kilo Code, Roo Code, Zoo Code, Kiro, Trae, OpenCode, Qwen
Code, Kimi Code, and Pi Agent.

</details>

> **Pi Coding Agent:** Install an MCP extension that reads
> `~/.pi/agent/mcp.json`; Pi has no built-in MCP support. See the
> [Pi package gallery](https://pi.dev/packages).

Clients use `godot-ai attach`, a client-owned stdio bridge that starts or reuses
the local backend and discovers its rotating private capability. The dock shows
the configured transport and, when needed, a copyable manual command. Clients
without a verified stdio or dynamic-capability surface are not advertised.

<details>
<summary><strong>Registering per-project instead of globally</strong></summary>

CLI-configured clients use global `user` scope by default. To limit Godot AI to
one project, set **Editor Settings → Plugins → `godot_ai/mcp_client_scope`** to
`project` (or `local`, where supported), then press **Configure** again.

> [!IMPORTANT]
> **Configure** removes existing `godot-ai` entries from every scope before
> writing the selected one. This can modify a checked-in `.mcp.json`, but never
> touches other server entries. **Remove** only affects the currently selected
> scope.

For `project` scope:

- The client CLI resolves the project config against **its own working
  directory**. Launch Godot from the project directory so `.mcp.json` lands
  where expected.
- Claude Code requires one-time approval: run `claude` in the project and
  accept the prompt.

Re-run **Configure** after changing ports, excluded domains, or plugin versions.

</details>

### 4. Try it

- *"Show me the current scene hierarchy."*
- *"Create a Camera3D named MainCamera under /Main."*
- *"Search the project for PackedScene files in ui/."*
- *"Run the scene test suite."*
- *"Build a voxel block-world game with a player, blocks to place and destroy, and save slots."*

<p align="center">
  <img src="docs/images/blockarena.gif" alt="Block-world game scene built from MCP tool calls — voxel terrain, player, and UI" width="640">
</p>
<p align="center"><em>Demo gamelet with sophisticated save system built from a handful of Godot AI MCP prompts. Code and Godot project  <a href="https://github.com/dsarno/save-system-godot-claude">available free here</a>.</em></p>

---

**Tools and resources:** see [docs/TOOLS.md](docs/TOOLS.md) for the generated tool, op, and resource inventory (46 tools exposing 120+ ops, plus read-only `godot://` resources), grouped by domain.

**Testing:** the plugin ships an in-editor GDScript test framework — your AI client (or you) can write `McpTestSuite` suites for your own game under `res://tests/` and run them with `test_run`. See [docs/testing.md](docs/testing.md).

<details>
<summary><strong>Manual Client Configuration</strong></summary>

Prefer the dock-generated command: it selects a compatible launcher and includes
the current version, ports, and excluded tool domains. Re-run **Configure**
after any of those values change.

The generated uvx-tier entry has this shape (shown here for Claude Desktop).
Keep the resolver flags: they prevent ambient uv configuration from selecting a
different source or tool environment. The dock may instead select a verified
development-venv or system-install tier and may add exclusions or the telemetry
opt-out, so its exact output remains authoritative.

```json
{
  "mcpServers": {
    "godot-ai": {
      "command": "/absolute/path/to/uvx",
      "args": [
        "--isolated", "--no-config", "--no-env-file", "--no-sources", "--no-build",
        "--index-strategy", "first-index", "--keyring-provider", "disabled",
        "--index", "https://pypi.org/simple",
        "--default-index", "https://pypi.org/simple",
        "--find-links", "https://pypi.org/simple/godot-ai/",
        "--link-mode", "copy", "--from", "godot-ai==VERSION",
        "godot-ai", "attach", "--port", "8000", "--ws-port", "9500"
      ]
    }
  }
}
```

Codex uses the same attach command in `~/.codex/config.toml`:

```toml
[mcp_servers."godot-ai"]
command = "/absolute/path/to/uvx"
args = [
  "--isolated", "--no-config", "--no-env-file", "--no-sources", "--no-build",
  "--index-strategy", "first-index", "--keyring-provider", "disabled",
  "--index", "https://pypi.org/simple",
  "--default-index", "https://pypi.org/simple",
  "--find-links", "https://pypi.org/simple/godot-ai/",
  "--link-mode", "copy",
  "--from", "godot-ai==VERSION",
  "godot-ai", "attach",
  "--port", "8000",
  "--ws-port", "9500",
]
enabled = true
startup_timeout_sec = 60
tool_timeout_sec = 360
```

On Windows, use the dock-generated entry so Store/MSIX paths and consoleless
launching are handled correctly. Other clients expose their exact config in
the dock's **Run this manually** panel.

These flags isolate resolution from ambient uv configuration; they do not
cryptographically bind later public package bytes. PyPI/TLS, the selected uv
executable and cache, and same-user machine integrity remain runtime trust
roots; see [Packaging and Distribution](docs/packaging-distribution.md).

A persistent bare `http://127.0.0.1:8000/mcp` entry is not valid in v4: it
cannot carry or rotate the private bearer capability. Use the dock-generated
stdio attach command.

</details>

<details>
<summary><strong>How It Works</strong></summary>

```text
MCP Client
   | stdio
   v
godot-ai attach
   | authenticated HTTP (/mcp)
   v
Python Server (FastMCP)      port 8000
   | WebSocket               port 9500
   v
Godot Editor Plugin
   | EditorInterface + SceneTree APIs
   v
Godot Editor
```

Both local hops use independent rotating capabilities. On POSIX, the bootstrap
record is owner-only and every path component is checked. On Windows, v4 uses
the fixed per-user location and rejects reparse traversal, but does not claim
secrecy or integrity against another local account or a process already running
as the same user. Neither a tokenless WebSocket nor a bare HTTP fallback exists
in v4.

</details>

<details>
<summary><strong>Remote / LAN access (<code>--allow-host</code>)</strong></summary>

The server binds to `127.0.0.1` by default. `--allow-host` may widen the HTTP
listener to trusted IPs or CIDRs, but it does not remove capability
authentication (repeat or comma-separate the flag):

```bash
godot-ai --transport streamable-http --allow-host 192.168.1.0/24
```

The editor WebSocket remains loopback-only. A remote client also needs a safe
way to invoke the attach bridge on the server host; never copy the rotating
capability into a persistent URL config. Prefer an SSH-launched stdio command
or a tunnel on untrusted networks.

</details>

<details>
<summary><strong>Legacy <code>mcp-proxy</code> import errors</strong></summary>

Update Godot AI, press **Configure** again, and restart the MCP client. This
replaces old `mcp-proxy` entries with the current `godot-ai attach` launcher.

</details>

<details>
<summary><strong>Windows: <code>uvx</code> or <code>pywin32</code> install errors</strong></summary>

Close Godot and the MCP client, reopen Godot, press **Configure**, then restart
the client. Configure uses `--link-mode copy`, and the plugin cleans stale uv
build directories to avoid Windows file-lock races. If the error persists,
stop stray Godot AI Python processes before retrying.

</details>

<details>
<summary><strong>Contributing</strong></summary>

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for development setup, testing, and
PR guidelines. AI assistants should also read [AGENTS.md](AGENTS.md).

**Windows:** run `.\script\setup-dev.ps1` in PowerShell; it creates the test
project junction without admin rights or Developer Mode.

</details>

<details>
<summary><strong>Telemetry &amp; Privacy</strong></summary>

Anonymous telemetry includes an installation UUID, event name, outcome,
duration, platform, and version. It excludes code, scene contents, project/file
names, and personal data; project-directory slugs are SHA-256 hashed.

Opt out by setting either environment variable to `true`:

```bash
export GODOT_AI_DISABLE_TELEMETRY=true
# or
export DISABLE_TELEMETRY=true
```

Opt-out creates no UUID, worker, or files. See [telemetry and privacy details](docs/TELEMETRY.md).

</details>

---

## Star History

<!-- Regenerated daily by .github/workflows/star-history.yml (#750):
     GitHub restricted stargazer history to repo collaborators, which broke
     star-history.com's unauthenticated embed, so the chart is rendered in CI
     and published to the dedicated `star-history` branch (do not delete it —
     embedded below; a manual workflow run recreates it if needed). -->
<a href="https://github.com/hi-godot/godot-ai/stargazers">
  <img src="https://raw.githubusercontent.com/hi-godot/godot-ai/star-history/star-history.svg" alt="Star History Chart" width="700">
</a>

---

**License:** [MIT](LICENSE) | **Issues:** [GitHub](https://github.com/hi-godot/godot-ai/issues)
