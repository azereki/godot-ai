"""Security contract for the local transport-capability bootstrap record."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from godot_ai.transport import capability as capability_module
from godot_ai.transport.capability import (
    HTTP_CAPABILITY_ENV,
    MAX_RECORD_BYTES,
    WS_CAPABILITY_ENV,
    PortClaimUnavailable,
    acquire_port_claim,
    capability_directory,
    generate_capabilities,
    launch_capabilities_from_env,
    read_capabilities,
    record_path,
    remove_capabilities,
    validate_launch_capabilities,
    validate_record,
    write_capabilities,
)

HTTP = "h" * 32
WEBSOCKET = "b" * 64
NONCE = "a" * 32


def test_generated_capabilities_are_distinct_and_valid() -> None:
    generated = generate_capabilities()

    assert validate_launch_capabilities(generated.http, generated.websocket) == generated
    assert generated.http != generated.websocket


@pytest.mark.skipif(os.name == "nt", reason="POSIX ancestor mode contract")
def test_only_root_owned_sticky_directory_is_safe_as_writable_ancestor() -> None:
    root_sticky = SimpleNamespace(st_mode=stat.S_IFDIR | 0o1777, st_uid=0)
    user_writable = SimpleNamespace(st_mode=stat.S_IFDIR | 0o0777, st_uid=os.getuid())
    other_sticky = SimpleNamespace(st_mode=stat.S_IFDIR | 0o1777, st_uid=os.getuid() + 1)

    assert capability_module._is_safe_posix_ancestor(Path("/tmp"), root_sticky)
    assert not capability_module._is_safe_posix_ancestor(Path("/tmp"), user_writable)
    assert not capability_module._is_safe_posix_ancestor(Path("/tmp"), other_sticky)
    assert not capability_module._is_safe_posix_ancestor(
        Path("/untrusted-sticky"), root_sticky
    )


@pytest.mark.parametrize("length", [31, 129])
def test_capability_length_is_bounded(length: int) -> None:
    with pytest.raises(ValueError, match="32-128"):
        validate_launch_capabilities("h" * length, WEBSOCKET)


def test_websocket_capability_has_one_canonical_encoding() -> None:
    for value in ("b" * 63, "B" * 64, "z" * 64):
        with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
            validate_launch_capabilities(HTTP, value)


def test_capability_rejects_header_injection() -> None:
    with pytest.raises(ValueError, match="ASCII bearer-token"):
        validate_launch_capabilities("secret\r\nX-Injected: yes", WEBSOCKET)


def test_launch_capabilities_require_one_complete_pair(monkeypatch) -> None:
    monkeypatch.setenv(HTTP_CAPABILITY_ENV, HTTP)
    monkeypatch.delenv(WS_CAPABILITY_ENV, raising=False)
    with pytest.raises(ValueError, match="supplied together"):
        launch_capabilities_from_env()

    monkeypatch.setenv(WS_CAPABILITY_ENV, WEBSOCKET)
    assert launch_capabilities_from_env() == validate_launch_capabilities(HTTP, WEBSOCKET)


def test_missing_pair_is_generated_only_when_explicitly_allowed(monkeypatch) -> None:
    monkeypatch.delenv(HTTP_CAPABILITY_ENV, raising=False)
    monkeypatch.delenv(WS_CAPABILITY_ENV, raising=False)

    with pytest.raises(ValueError, match="required"):
        launch_capabilities_from_env(generate_if_missing=False)

    generated = launch_capabilities_from_env()
    assert generated.http != generated.websocket


def test_record_round_trips_as_one_private_canonical_value(tmp_path) -> None:
    directory = tmp_path / "capabilities"
    path = write_capabilities(8122, HTTP, WEBSOCKET, instance_nonce=NONCE, directory=directory)

    assert read_capabilities(8122, directory) == validate_record(HTTP, WEBSOCKET, NONCE)
    assert json.loads(path.read_text(encoding="ascii")) == {
        "version": 1,
        "http": HTTP,
        "websocket": WEBSOCKET,
        "instance_nonce": NONCE,
    }
    if os.name != "nt":
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_port_claim_excludes_a_second_owner_until_release(tmp_path) -> None:
    first = acquire_port_claim(8123, tmp_path)
    try:
        with pytest.raises(PortClaimUnavailable):
            acquire_port_claim(8123, tmp_path)
    finally:
        first.release()

    acquire_port_claim(8123, tmp_path).release()


def test_record_removal_is_bound_to_the_published_instance(tmp_path) -> None:
    write_capabilities(8123, HTTP, WEBSOCKET, instance_nonce=NONCE, directory=tmp_path)

    assert remove_capabilities(8123, "b" * 32, tmp_path) is False
    assert read_capabilities(8123, tmp_path) is not None
    assert remove_capabilities(8123, NONCE, tmp_path) is True
    assert read_capabilities(8123, tmp_path) is None


@pytest.mark.parametrize("port", [0, 65536])
def test_record_path_rejects_invalid_ports(port: int, tmp_path) -> None:
    with pytest.raises(ValueError, match="between 1 and 65535"):
        record_path(port, tmp_path)


@pytest.mark.parametrize(
    "raw",
    [
        f'{{"version":1,"http":"{HTTP}","websocket":"{WEBSOCKET}"}}',
        f'{{"version":1,"http":"{HTTP}","websocket":"{WEBSOCKET}","instance_nonce":"{NONCE}","extra":1}}',
        f'{{"version":1,"version":1,"http":"{HTTP}","websocket":"{WEBSOCKET}","instance_nonce":"{NONCE}"}}',
        f'{{"version":true,"http":"{HTTP}","websocket":"{WEBSOCKET}","instance_nonce":"{NONCE}"}}',
        f'{{"version":1,"http":"{HTTP}","websocket":"{HTTP}","instance_nonce":"{NONCE}"}}',
        f'{{"version":1,"http":"{HTTP}","websocket":"{WEBSOCKET}","instance_nonce":"not-hex"}}',
    ],
    ids=["missing", "extra", "duplicate", "boolean", "shared", "nonce"],
)
def test_record_rejects_partial_or_ambiguous_schema(raw: str, tmp_path) -> None:
    path = write_capabilities(8124, HTTP, WEBSOCKET, instance_nonce=NONCE, directory=tmp_path)
    path.write_text(raw, encoding="ascii")

    assert read_capabilities(8124, tmp_path) is None


def test_record_rejects_oversize_and_non_ascii(tmp_path) -> None:
    path = write_capabilities(8125, HTTP, WEBSOCKET, instance_nonce=NONCE, directory=tmp_path)
    for raw in (b"x" * (MAX_RECORD_BYTES + 2), "café".encode()):
        path.write_bytes(raw)
        assert read_capabilities(8125, tmp_path) is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX link and mode contract")
def test_record_rejects_leaf_link_and_permissive_mode(tmp_path) -> None:
    directory = tmp_path / "capabilities"
    path = write_capabilities(8126, HTTP, WEBSOCKET, instance_nonce=NONCE, directory=directory)
    path.chmod(0o644)
    assert read_capabilities(8126, directory) is None

    target = tmp_path / "target"
    target.write_text(path.read_text(encoding="ascii"), encoding="ascii")
    target.chmod(0o600)
    path.unlink()
    path.symlink_to(target)
    assert read_capabilities(8126, directory) is None


@pytest.mark.skipif(os.name == "nt", reason="POSIX link contract")
def test_record_rejects_linked_directory_component(tmp_path) -> None:
    real = tmp_path / "real"
    linked = tmp_path / "linked"
    real.mkdir()
    linked.symlink_to(real, target_is_directory=True)

    with pytest.raises(OSError, match="link or reparse"):
        write_capabilities(8127, HTTP, WEBSOCKET, instance_nonce=NONCE, directory=linked)


@pytest.mark.skipif(os.name == "nt", reason="POSIX ancestor mode contract")
def test_capability_directory_override_rejects_writable_ancestor(monkeypatch, tmp_path) -> None:
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir(mode=0o700)
    unsafe.chmod(0o777)
    monkeypatch.setenv("GODOT_AI_CAPABILITY_DIR", str(unsafe / "records"))

    with pytest.raises(OSError, match="unsafe ancestor"):
        capability_directory()


@pytest.mark.skipif(os.name == "nt", reason="POSIX ancestor owner contract")
def test_capability_directory_override_rejects_other_owner(monkeypatch, tmp_path) -> None:
    other_owned = os.stat_result((stat.S_IFDIR | 0o755, 0, 0, 0, os.getuid() + 1, 0, 0, 0, 0, 0))
    monkeypatch.setenv("GODOT_AI_CAPABILITY_DIR", str(tmp_path / "records"))
    monkeypatch.setattr(type(tmp_path), "lstat", lambda _path: other_owned)

    with pytest.raises(OSError, match="unsafe ancestor"):
        capability_directory()


@pytest.mark.skipif(os.name == "nt", reason="POSIX XDG path contract")
def test_capability_directory_rejects_relative_xdg(monkeypatch) -> None:
    monkeypatch.delenv("GODOT_AI_CAPABILITY_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/config")
    monkeypatch.setattr(capability_module.sys, "platform", "linux")

    with pytest.raises(ValueError, match="XDG_CONFIG_HOME must be an absolute path"):
        capability_directory()


@pytest.mark.skipif(os.name == "nt", reason="POSIX XDG ancestor mode contract")
def test_default_xdg_capability_directory_rejects_writable_ancestor(
    monkeypatch, tmp_path
) -> None:
    unsafe = tmp_path / "unsafe-xdg-parent"
    unsafe.mkdir(mode=0o700)
    unsafe.chmod(0o777)
    monkeypatch.delenv("GODOT_AI_CAPABILITY_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(unsafe / "xdg"))
    monkeypatch.setattr(capability_module.sys, "platform", "linux")

    with pytest.raises(OSError, match="unsafe ancestor"):
        capability_directory()


@pytest.mark.skipif(os.name == "nt", reason="POSIX explicit-directory contract")
def test_explicit_capability_directory_rejects_writable_ancestor(tmp_path) -> None:
    unsafe = tmp_path / "unsafe-explicit-parent"
    unsafe.mkdir(mode=0o700)
    unsafe.chmod(0o777)

    with pytest.raises(OSError, match="unsafe ancestor"):
        record_path(8128, unsafe / "records")
