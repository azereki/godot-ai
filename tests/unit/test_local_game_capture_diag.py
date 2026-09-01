from __future__ import annotations

import runpy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "script" / "local-game-capture-diag"
MODULE = runpy.run_path(str(SCRIPT))


@pytest.mark.parametrize(
    "url",
    (
        "http://127.0.0.1:8000/mcp",
        "http://localhost:8000/mcp",
        "http://[::1]:8000/mcp",
    ),
)
def test_diagnostic_accepts_only_credential_safe_loopback_urls(url: str) -> None:
    assert MODULE["_validated_loopback_url"](url) == url


@pytest.mark.parametrize(
    "url",
    (
        "https://127.0.0.1:8000/mcp",
        "http://example.com:8000/mcp",
        "http://user:pass@127.0.0.1:8000/mcp",
        "http://127.0.0.1:not-a-port/mcp",
    ),
)
def test_diagnostic_rejects_urls_that_could_expose_the_capability(url: str) -> None:
    with pytest.raises(ValueError):
        MODULE["_validated_loopback_url"](url)


def test_diagnostic_disables_redirect_following() -> None:
    handler = MODULE["_NoRedirectHandler"]()
    assert handler.redirect_request(None, None, 302, "Found", {}, "http://example.com") is None
