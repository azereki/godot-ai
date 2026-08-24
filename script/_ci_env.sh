## Shared env preamble for every ``script/ci-*`` runner. Sourced from the
## top of each ci-* script via ``source "$(dirname "$0")/_ci_env.sh"``.
##
## Match the workflow ``env:`` block opt-out for telemetry: no fake
## "installs" or stray streaming-insert quota from local dev runs of
## these scripts either. The collector treats this flag as a hard
## opt-out (no UUID generated, no worker thread, no _send). See
## docs/TELEMETRY.md.
export GODOT_AI_DISABLE_TELEMETRY=true

## Every ci-* runner reaches the MCP server through this URL. The default is
## the plugin's default port; override it when the connected editor's
## ``godot_ai/http_port`` is something else — the editor log names the port
## in its ``MCP | started server ... --port N`` line. The Python runners
## (ci-game-capture-smoke, local-game-capture-diag) read the same variable.
export MCP_SERVER_URL="${MCP_SERVER_URL:-http://127.0.0.1:8000/mcp}"
