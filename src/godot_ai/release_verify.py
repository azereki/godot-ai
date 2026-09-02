"""Strict, dependency-free verification and staging for signed v4 releases."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import shutil
import stat
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, NoReturn

REPOSITORY = "hi-godot/godot-ai"
ASSET_NAME = "godot-ai-v4-plugin.zip"
MANIFEST_NAME = "godot-ai-v4-plugin.manifest.json"
SIGNATURE_NAME = "godot-ai-v4-plugin.manifest.sig"
PLUGIN_PREFIX = "addons/godot_ai/"
PLUGIN_CONFIG = f"{PLUGIN_PREFIX}plugin.cfg"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
FIXED_MODE = stat.S_IFREG | 0o644
MAX_FILES = 4096
MAX_FILE_SIZE = 64 * 1024 * 1024
MAX_ARCHIVE_SIZE = 64 * 1024 * 1024
MAX_TREE_SIZE = MAX_ARCHIVE_SIZE
MAX_MANIFEST_SIZE = 1024 * 1024
SIGNATURE_SIZE = 512
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
VERSION = re.compile(r"^4\.\d+\.\d+$")
RESERVED = set("CON PRN AUX NUL CONIN$ CONOUT$".split()) | {
    f"{kind}{number}"
    for kind in ("COM", "LPT")
    for number in (*range(1, 10), "¹", "²", "³")
}
IDENTITY_KEYS = ("repository", "channel", "tag", "version", "source_commit")
ROOT_KEYS = {"schema_version", "asset", "inventory", *IDENTITY_KEYS}
PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAr4OmbONFTONGFcXSUQ2p
e54YaUhWDA75wxeDWhOc476vsdo53YnXEFT7EPr2hUKqeNxv++LqKOkFuAsxSNZy
wBe6P1tmQA4Og6Ezv4CGnZdEj1uhlDJFK9ShQ29oWfC6bf/84625SvvBxZos2Br9
yPKl7h5wzqDoeUSpv+f0ynTiC0i/HAUo/NQBlkgGwkomK2Fr3pP1VDxxq2xvgHSk
lU6Qcomr9WjJxI+HkDN5tRPPn0pDrg6YFx2J18OfD8KIa/kMGxuXOcHlPyRYpjyu
qTtg2oL0NyUIG+1TmJ3DcN4GlKC55eOrkfJ04vudS5pxdnUIFRmkGBXZLdaetoPc
ixtlD4w6gi8KIH1CTG+/TtHP1KVdOogCWDcjRCAmMJPFZe6eEKXmGQUZDb9wfnbx
h++XiVe5tq83BTLWmaFTy+fZbNo12uhNCNS1LJ42/yj+S1xvo0yMbkkNr1hIYk0P
584XnBQeBSVJDf3667NZXaxnWv94K9zbb+1OvOvPwhbOdgi2Ymcw5QEOQIavtg86
XLLcWzG+SJsycz1imikjv6sStWh8WHneKSTMq6A7V6PBj7oJyEJp10696BDw287k
YlH+9VGqowPEMXpWX57wOBKiWb4K1kw1LfxjT8W1e/pcX9pJqiv0DkjTXUxo9CDG
1X1+ZXBBR3MkGuFAOCjy0x8CAwEAAQ==
-----END PUBLIC KEY-----
"""
PUBLIC_KEY_SPKI_SHA256 = "84ebbd811f3a12c09ff4e236bbbbb9310fc23e03fcfc3717ba546747d0d21072"


class ReleaseError(RuntimeError):
    """A release input or verification failed."""


def _fail(context: str, message: str) -> NoReturn:
    raise ReleaseError(f"{context}: {message}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ReleaseError("duplicate JSON key")
    return result


def _strict_json(raw: bytes, context: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_strict_object,
            parse_constant=lambda value: _fail(context, f"non-standard JSON constant {value}"),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"{context}: invalid JSON: {exc}") from exc


def _canonical(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReleaseError(f"canonical JSON: invalid value: {exc}") from exc


def _object(value: Any, context: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _fail(context, f"expected object with exactly keys {sorted(keys)!r}")
    return value


def _string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(context, "expected non-empty string")
    return value


def _integer(value: Any, context: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        _fail(context, f"expected integer in [0, {maximum}]")
    return value


def _identity(repository: str, channel: str, tag: str, version: str, source: str) -> None:
    if repository != REPOSITORY:
        _fail("repository", f"expected {REPOSITORY!r}")
    if channel != "stable":
        _fail("channel", "v4 releases are stable-only")
    if not VERSION.fullmatch(version) or tag != f"v{version}":
        _fail("tag/version", "expected matching v4 tag and version")
    if not COMMIT.fullmatch(source):
        _fail("source_commit", "expected 40 lowercase hex characters")


def _safe_path(path: str, context: str) -> str:
    try:
        path.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ReleaseError(f"{context}: path is not valid UTF-8") from exc
    if not path.startswith(PLUGIN_PREFIX) or path.endswith("/") or "\\" in path:
        _fail(context, f"path must be a file beneath {PLUGIN_PREFIX}")
    for part in path.split("/"):
        if not part or part in {".", ".."} or part[-1] in {" ", "."}:
            _fail(context, "unsafe path component")
        if any(ord(char) < 32 or char in '<>:"|?*' for char in part):
            _fail(context, "unsafe path character")
        if part.split(".", 1)[0].upper() in RESERVED:
            _fail(context, "reserved path component")
    return unicodedata.normalize("NFC", path).casefold()


def _validate_paths(paths: list[str], context: str) -> None:
    if not paths or len(paths) > MAX_FILES or paths != sorted(paths):
        _fail(context, f"expected 1..{MAX_FILES} paths in bytewise order")
    identities: set[str] = set()
    exact = set(paths)
    for index, path in enumerate(paths):
        identity = _safe_path(path, f"{context}[{index}]")
        if identity in identities:
            _fail(context, "case/Unicode-colliding paths")
        identities.add(identity)
        parent = path.rsplit("/", 1)[0]
        while "/" in parent:
            if parent in exact:
                _fail(context, "file/ancestor collision")
            parent = parent.rsplit("/", 1)[0]


def _plugin_version(data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReleaseError("plugin.cfg: expected UTF-8") from exc
    matches = re.findall(r'^\s*version\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    if len(matches) != 1:
        _fail("plugin.cfg", "expected exactly one quoted version")
    return matches[0]


def _hash_file(path: Path, maximum: int) -> tuple[int, str]:
    digest, size = hashlib.sha256(), 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                size += len(chunk)
                if size > maximum:
                    _fail(str(path), f"exceeds {maximum}-byte bound")
                digest.update(chunk)
    except OSError as exc:
        raise ReleaseError(f"{path}: cannot read: {exc}") from exc
    return size, digest.hexdigest()


def _read_bounded(path: Path, maximum: int, *, allow_empty: bool = False) -> bytes:
    try:
        with path.open("rb") as handle:
            data = handle.read(maximum + 1)
    except OSError as exc:
        raise ReleaseError(f"{path}: cannot read: {exc}") from exc
    if (not data and not allow_empty) or len(data) > maximum:
        _fail(str(path), f"expected 1..{maximum} bytes")
    return data


def _der_item(data: bytes, offset: int, tag: int, context: str) -> tuple[bytes, int]:
    if offset >= len(data) or data[offset] != tag:
        _fail(context, f"expected DER tag 0x{tag:02x}")
    offset += 1
    if offset >= len(data):
        _fail(context, "truncated DER length")
    first, offset = data[offset], offset + 1
    if first < 0x80:
        length = first
    else:
        count = first & 0x7F
        if not 1 <= count <= 4 or offset + count > len(data) or data[offset] == 0:
            _fail(context, "invalid DER length")
        length = int.from_bytes(data[offset : offset + count], "big")
        offset += count
        if length < 0x80:
            _fail(context, "non-canonical DER length")
    end = offset + length
    if end > len(data):
        _fail(context, "truncated DER value")
    return data[offset:end], end


def _rsa_public_numbers(public_key: str) -> tuple[int, int]:
    lines = public_key.strip().splitlines()
    if (
        len(lines) < 3
        or lines[0] != "-----BEGIN PUBLIC KEY-----"
        or lines[-1] != "-----END PUBLIC KEY-----"
    ):
        _fail("public key", "expected a PEM SubjectPublicKeyInfo")
    try:
        der = base64.b64decode("".join(lines[1:-1]), validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ReleaseError("public key: invalid PEM encoding") from exc
    outer, end = _der_item(der, 0, 0x30, "public key")
    if end != len(der):
        _fail("public key", "trailing DER data")
    algorithm, offset = _der_item(outer, 0, 0x30, "public key algorithm")
    if algorithm != bytes.fromhex("06092a864886f70d0101010500"):
        _fail("public key", "expected rsaEncryption with NULL parameters")
    bits, offset = _der_item(outer, offset, 0x03, "public key bits")
    if offset != len(outer) or not bits or bits[0] != 0:
        _fail("public key", "invalid subjectPublicKey bit string")
    key, key_end = _der_item(bits, 1, 0x30, "RSA public key")
    if key_end != len(bits):
        _fail("public key", "trailing RSA key data")

    def integer(position: int, name: str) -> tuple[int, int]:
        raw, position = _der_item(key, position, 0x02, name)
        if not raw or raw[0] & 0x80 or (len(raw) > 1 and raw[0] == 0 and not raw[1] & 0x80):
            _fail(name, "expected a canonical positive INTEGER")
        return int.from_bytes(raw, "big"), position

    modulus, position = integer(0, "RSA modulus")
    exponent, position = integer(position, "RSA exponent")
    if position != len(key) or exponent < 3 or exponent % 2 == 0:
        _fail("public key", "invalid RSA public numbers")
    if (modulus.bit_length() + 7) // 8 != SIGNATURE_SIZE:
        _fail("public key", f"expected a {SIGNATURE_SIZE * 8}-bit RSA key")
    return modulus, exponent


def _verify_signature(manifest: bytes, data: bytes, public_key: str) -> None:
    if len(data) != SIGNATURE_SIZE:
        _fail("manifest signature", f"expected exactly {SIGNATURE_SIZE} bytes")
    modulus, exponent = _rsa_public_numbers(public_key)
    number = int.from_bytes(data, "big")
    if number >= modulus:
        _fail("manifest signature", "signature representative is outside the RSA modulus")
    encoded = pow(number, exponent, modulus).to_bytes(SIGNATURE_SIZE, "big")
    digest_info = (
        bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(manifest).digest()
    )
    padding = SIGNATURE_SIZE - len(digest_info) - 3
    expected = b"\x00\x01" + b"\xff" * padding + b"\x00" + digest_info
    if padding < 8 or encoded != expected:
        _fail("manifest signature", "RSA PKCS#1 v1.5 SHA-256 verification failed")


def _validate_manifest(raw: bytes, expected: tuple[str, str, str, str, str]) -> dict[str, Any]:
    manifest = _strict_json(raw, "manifest")
    if raw != _canonical(manifest):
        _fail("manifest", "encoding is not canonical JSON")
    root = _object(manifest, "manifest", ROOT_KEYS)
    if _integer(root["schema_version"], "manifest.schema_version", 1) != 1:
        _fail("manifest.schema_version", "expected 1")
    identity = tuple(_string(root[key], f"manifest.{key}") for key in IDENTITY_KEYS)
    _identity(*identity)
    if identity != expected:
        _fail("manifest", "release identity does not match the explicit expectation")
    asset = _object(root["asset"], "manifest.asset", {"name", "size", "sha256"})
    if asset["name"] != ASSET_NAME:
        _fail("manifest.asset.name", f"expected {ASSET_NAME!r}")
    _integer(asset["size"], "manifest.asset.size", MAX_ARCHIVE_SIZE)
    if not SHA256.fullmatch(_string(asset["sha256"], "manifest.asset.sha256")):
        _fail("manifest.asset.sha256", "expected 64 lowercase hex characters")
    rows = root["inventory"]
    if not isinstance(rows, list):
        _fail("manifest.inventory", "expected array")
    paths, total = [], 0
    for index, value in enumerate(rows):
        row = _object(value, f"manifest.inventory[{index}]", {"path", "size", "sha256"})
        paths.append(_string(row["path"], f"manifest.inventory[{index}].path"))
        total += _integer(row["size"], f"manifest.inventory[{index}].size", MAX_FILE_SIZE)
        if not SHA256.fullmatch(_string(row["sha256"], f"manifest.inventory[{index}].sha256")):
            _fail(f"manifest.inventory[{index}].sha256", "expected 64 lowercase hex characters")
    _validate_paths(paths, "manifest.inventory")
    if total > MAX_TREE_SIZE or PLUGIN_CONFIG not in paths:
        _fail("manifest.inventory", "missing plugin.cfg or expanded tree exceeds bound")
    return root


def _verify_archive(data: bytes, manifest: dict[str, Any]) -> None:
    expected = {row["path"]: row for row in manifest["inventory"]}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if archive.comment or [info.filename for info in infos] != list(expected):
                _fail("archive", "entries do not exactly match the sorted inventory")
            config = b""
            for info in infos:
                row = expected[info.filename]
                if (
                    info.is_dir()
                    or info.create_system != 3
                    or info.date_time != FIXED_TIME
                    or info.external_attr >> 16 != FIXED_MODE
                    or info.compress_type != zipfile.ZIP_STORED
                    or info.compress_size != info.file_size
                    or info.flag_bits & ~0x800
                    or info.extra
                    or info.comment
                ):
                    _fail(info.filename, "unsafe or non-canonical ZIP metadata")
                if info.file_size != row["size"]:
                    _fail(info.filename, "size differs from inventory")
                data = archive.read(info)
                if len(data) != row["size"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
                    _fail(info.filename, "content differs from inventory")
                if info.filename == PLUGIN_CONFIG:
                    config = data
            if _plugin_version(config) != manifest["version"]:
                _fail("plugin.cfg", "version differs from signed manifest")
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ReleaseError(f"archive: invalid ZIP: {exc}") from exc


def _load_verified_release(
    archive: Path,
    manifest_path: Path,
    signature: Path,
    expected: tuple[str, str, str, str, str],
) -> tuple[bytes, bytes, dict[str, Any]]:
    """Freeze and authenticate each mutable input exactly once."""

    raw = _read_bounded(manifest_path, MAX_MANIFEST_SIZE)
    signature_data = _read_bounded(signature, SIGNATURE_SIZE)
    archive_data = _read_bounded(archive, MAX_ARCHIVE_SIZE)
    manifest = _validate_manifest(raw, expected)
    _verify_signature(raw, signature_data, PUBLIC_KEY_PEM)
    if (
        len(archive_data) != manifest["asset"]["size"]
        or hashlib.sha256(archive_data).hexdigest() != manifest["asset"]["sha256"]
    ):
        _fail("archive", "size or SHA-256 differs from signed manifest")
    _verify_archive(archive_data, manifest)
    return archive_data, raw, manifest


def verify_release(
    archive: Path,
    manifest_path: Path,
    signature: Path,
    expected: tuple[str, str, str, str, str],
) -> dict[str, Any]:
    _archive, _raw, manifest = _load_verified_release(archive, manifest_path, signature, expected)
    return manifest


def _safe_posix_ancestor(uid: int, mode: int) -> bool:
    permissions = stat.S_IMODE(mode)
    root_sticky = uid == 0 and stat.S_ISDIR(mode) and bool(permissions & stat.S_ISVTX)
    return uid in {0, os.getuid()} and not (permissions & 0o022 and not root_sticky)


def _safe_directory(path: Path, context: str) -> Path:
    absolute = Path(os.path.abspath(path.expanduser()))
    current = Path(absolute.anchor)
    try:
        for part in absolute.parts[1:]:
            current /= part
            info = current.lstat()
            if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
                _fail(context, f"path crosses a link or reparse point: {current}")
            if os.name != "nt" and not _safe_posix_ancestor(info.st_uid, info.st_mode):
                _fail(context, f"path has an unsafe POSIX ancestor: {current}")
        resolved = absolute.resolve(strict=True)
        if not stat.S_ISDIR(resolved.lstat().st_mode):
            _fail(context, "expected a directory")
        return resolved
    except FileNotFoundError as exc:
        raise ReleaseError(f"{context}: path does not exist: {exc.filename}") from exc
    except OSError as exc:
        raise ReleaseError(f"{context}: cannot inspect path: {exc}") from exc


def _tree_identity(root: Path, context: str) -> tuple[str, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    total = 0
    try:
        for current, directories, files in os.walk(
            root, onerror=lambda error: _fail(context, str(error))
        ):
            parent = Path(current)
            for name in directories:
                if not stat.S_ISDIR((parent / name).lstat().st_mode):
                    _fail(context, f"non-directory or link: {parent / name}")
            for name in files:
                path = parent / name
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode):
                    _fail(context, f"non-regular file or link: {path}")
                if os.name != "nt" and info.st_nlink != 1:
                    _fail(context, f"hard-linked file cannot be retained safely: {path}")
                size, digest = _hash_file(path, MAX_FILE_SIZE)
                total += size
                if len(rows) >= MAX_FILES or total > MAX_TREE_SIZE:
                    _fail(context, "tree exceeds migration bounds")
                rows.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "size": size,
                        "sha256": digest,
                    }
                )
    except OSError as exc:
        raise ReleaseError(f"{context}: cannot inspect tree: {exc}") from exc
    rows.sort(key=lambda row: row["path"])
    return hashlib.sha256(_canonical(rows)).hexdigest(), rows


def _verify_installed_tree(root: Path, manifest: dict[str, Any]) -> None:
    _digest, actual = _tree_identity(root, "installed v4 tree")
    expected = [{**row, "path": row["path"][len(PLUGIN_PREFIX) :]} for row in manifest["inventory"]]
    if actual != expected:
        _fail("installed v4 tree", "files do not exactly match the signed inventory")


def _extract_verified_archive(archive_data: bytes, destination: Path) -> Path:
    plugin_root = destination / "addons" / "godot_ai"
    try:
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            for info in archive.infolist():
                target = plugin_root.joinpath(*info.filename[len(PLUGIN_PREFIX) :].split("/"))
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(target, flags, 0o600)
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(archive.read(info))
                    handle.flush()
                    os.fsync(handle.fileno())
                if os.name != "nt":
                    target.chmod(0o600)
        return plugin_root
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ReleaseError(f"staging: extraction failed: {exc}") from exc


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sync_staged_directories(destination: Path) -> None:
    directories = [path for path in destination.rglob("*") if path.is_dir()]
    directories.sort(key=lambda path: len(path.parts), reverse=True)
    for directory in (*directories, destination):
        _sync_directory(directory)


def stage_verified_release(
    archive: Path,
    manifest_path: Path,
    signature: Path,
    expected: tuple[str, str, str, str, str],
    destination: Path,
) -> tuple[Path, str, dict[str, Any]]:
    """Verify frozen bytes and extract one new exact tree, without touching live."""

    archive_data, manifest_raw, manifest = _load_verified_release(
        archive, manifest_path, signature, expected
    )
    if os.path.lexists(destination):
        _fail("staging", "destination already exists")
    destination.mkdir(mode=0o700)
    _sync_directory(destination.parent)
    try:
        plugin = _extract_verified_archive(archive_data, destination)
        _verify_installed_tree(plugin, manifest)
        _sync_staged_directories(destination)
        digest = hashlib.sha256(manifest_raw).hexdigest()
        return plugin, digest, manifest
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        _sync_directory(destination.parent)
        raise
