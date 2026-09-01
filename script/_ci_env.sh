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

ci_load_http_auth() {
  local capability
  capability=$("${PYTHON_CMD:-python}" - "$MCP_SERVER_URL" <<'PY'
import os
import sys
from urllib.parse import urlsplit

from godot_ai.transport.capability import (
    HTTP_CAPABILITY_ENV,
    read_capabilities,
    validate_capability,
)

target = urlsplit(sys.argv[1])
if target.hostname in {"127.0.0.1", "localhost", "::1"}:
    port = target.port or (443 if target.scheme == "https" else 80)
    record = read_capabilities(port)
    if record is None:
        raise SystemExit("missing Godot AI HTTP capability record")
    capability = record.http
else:
    try:
        capability = validate_capability(os.environ.get(HTTP_CAPABILITY_ENV, ""))
    except ValueError as exc:
        raise SystemExit(f"invalid {HTTP_CAPABILITY_ENV}: {exc}") from None
print(capability)
PY
  ) || return 1
  HTTP_AUTH_CAPABILITY="$capability"
  HTTP_AUTH_HEADERS=(-H "Authorization: Bearer $capability")
  unset capability
}
