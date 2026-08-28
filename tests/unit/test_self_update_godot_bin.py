"""Unit tests for GODOT_BIN resolution in the self-update fixture.

Issue #917: when CI sets GODOT_BIN to a name that does not resolve,
pytest.skip() made the whole step exit 0 with zero tests executed.
Unset still skips so a local run without an engine stays optional.
"""

from __future__ import annotations

import pytest

from tests.integration._self_update_fixture import godot_bin_or_skip


def test_godot_bin_unset_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GODOT_BIN", raising=False)

    with pytest.raises(pytest.skip.Exception, match="GODOT_BIN is not set"):
        godot_bin_or_skip()


def test_godot_bin_set_but_unresolvable_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GODOT_BIN", "godot-ai-missing-binary-917")
    monkeypatch.setattr(
        "tests.integration._self_update_fixture.shutil.which",
        lambda _name: None,
    )

    with pytest.raises(pytest.fail.Exception, match="does not resolve"):
        godot_bin_or_skip()
