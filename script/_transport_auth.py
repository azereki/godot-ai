"""Read the current HTTP capability for repository smoke clients."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from godot_ai.transport.capability import (
    HTTP_CAPABILITY_ENV,
    read_capabilities,
    validate_capability,
)


def authorization_header(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        record = read_capabilities(port)
        if record is None:
            raise RuntimeError(f"no valid Godot AI capability record for HTTP port {port}")
        capability = record.http
    else:
        capability = validate_capability(os.environ.get(HTTP_CAPABILITY_ENV, ""))
    return f"Bearer {capability}"
