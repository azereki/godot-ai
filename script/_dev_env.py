"""Shared cross-platform helpers for the dev scripts (stormtest, serve-this-worktree).

POSIX/Windows differences — the venv interpreter layout (``bin/python`` vs
``Scripts\\python.exe``) and port freeing (``lsof`` vs ``netstat``/``taskkill``)
— are resolved here so the *documented* commands are identical on every OS and
no script carries a hard ``bash``/``lsof`` dependency. See issue #509.

stdlib-only and side-effect-free on import, so it is safe to import from a test
or before a script re-execs into the venv.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


# --------------------------------------------------------------------------- #
# venv interpreter resolution
# --------------------------------------------------------------------------- #
def venv_python(venv_dir: Path, *, windows: bool | None = None) -> Path:
    """Interpreter path inside ``venv_dir`` for the target OS.

    ``windows`` defaults to the current platform; pass it explicitly to resolve
    the other layout (used by tests so the Windows branch is covered on POSIX CI).
    """
    if windows is None:
        windows = os.name == "nt"
    if windows:
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _git(args: list[str], cwd: Path) -> str | None:
    """Run a read-only git command, returning trimmed stdout or ``None`` on error."""
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def worktree_root(start: Path | None = None) -> Path:
    """Top of the current git worktree; falls back to this file's repo root."""
    start = start or Path.cwd()
    top = _git(["rev-parse", "--show-toplevel"], start)
    if top:
        return Path(top)
    # script/_dev_env.py -> repo root
    return Path(__file__).resolve().parent.parent


def _root_from_common_dir(worktree: Path, common_dir: str) -> Path:
    """Parent of the git common dir (the main repo that owns the shared .venv)."""
    common = Path(common_dir)
    if not common.is_absolute():
        common = (worktree / common).resolve()
    return common.parent


def root_repo(worktree: Path | None = None) -> Path:
    """Main repo dir holding the shared ``.venv`` (handles git worktrees).

    In a worktree the ``.venv`` lives in the main checkout, not the worktree, so
    ``git rev-parse --git-common-dir`` (whose parent is the main repo) is used to
    find it. On the main checkout this collapses to the worktree itself.
    """
    wt = worktree or worktree_root()
    common = _git(["rev-parse", "--git-common-dir"], wt)
    if common:
        return _root_from_common_dir(wt, common)
    return wt


def worktree_src(worktree: Path | None = None) -> Path:
    """The ``src/`` directory of the given (or current) worktree."""
    return (worktree or worktree_root()) / "src"


def find_venv_python(worktree: Path | None = None) -> Path | None:
    """Locate the checkout's venv interpreter, or ``None`` if it doesn't exist."""
    candidate = venv_python(root_repo(worktree) / ".venv")
    return candidate if candidate.exists() else None


def reexec_into_venv(*, guard_env: str, opt_out_env: str | None = None) -> None:
    """Re-exec the current script under the project venv interpreter.

    No-op when: the venv is absent, we're already running it, ``guard_env`` is
    set (re-exec already happened, so we never loop), or ``opt_out_env`` is set.
    Lets a script's documented invocation be ``python <script>`` on every OS — it
    hops into the venv itself instead of the caller naming ``bin/python`` vs
    ``Scripts\\python.exe``.
    """
    if os.environ.get(guard_env):
        return
    if opt_out_env and os.environ.get(opt_out_env):
        return
    target = find_venv_python()
    if target is None:
        return
    try:
        if target.resolve() == Path(sys.executable).resolve():
            return
    except OSError:
        return
    os.environ[guard_env] = "1"
    os.execv(str(target), [str(target), *sys.argv])


# --------------------------------------------------------------------------- #
# port freeing (replace a plugin-spawned server instead of stacking on it)
# --------------------------------------------------------------------------- #
def extract_port(argv: list[str], default: int = 8000) -> tuple[int, list[str]]:
    """Pull ``--port N`` / ``--port=N`` out of ``argv``.

    Returns ``(port, remaining_args)`` with the port flag removed, so the caller
    can pass the port explicitly (and free it) without duplicating the flag.
    """
    port = default
    rest: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--port" and i + 1 < len(argv):
            try:
                port = int(argv[i + 1])
            except ValueError:
                pass
            i += 2
            continue
        if arg.startswith("--port="):
            try:
                port = int(arg.split("=", 1)[1])
            except ValueError:
                pass
            i += 1
            continue
        rest.append(arg)
        i += 1
    return port, rest


def parse_lsof_pids(output: str) -> list[int]:
    """PIDs from ``lsof -ti`` output (one PID per line), de-duplicated."""
    pids: list[int] = []
    for token in output.split():
        token = token.strip()
        if token.isdigit() and int(token) not in pids:
            pids.append(int(token))
    return pids


def parse_netstat_pids(output: str, port: int) -> list[int]:
    """Listener PIDs for ``port`` from Windows ``netstat -ano`` output."""
    needle = f":{port}"
    pids: list[int] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5 or "LISTENING" not in parts:
            continue
        local = parts[1]  # e.g. 0.0.0.0:8000 or [::]:8000
        if not local.endswith(needle):
            continue
        pid = parts[-1]
        if pid.isdigit() and int(pid) not in pids:
            pids.append(int(pid))
    return pids


def _port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _listener_pids(port: int) -> list[int]:
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
            ).stdout
            return parse_netstat_pids(out, port)
        out = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
        ).stdout
        return parse_lsof_pids(out)
    except (OSError, subprocess.SubprocessError):
        return []


def _kill_pid(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        pass


def free_port(port: int) -> None:
    """Best-effort: stop any process currently listening on ``port``.

    Cross-platform replacement for the bash ``lsof | xargs kill`` dance. Silent
    and non-fatal if the port is free or the listener can't be identified.
    """
    if not _port_listening(port):
        return
    print(f"Stopping existing listener on port {port}")
    for pid in _listener_pids(port):
        _kill_pid(pid)
    # Give the socket a moment to release before the caller binds it.
    time.sleep(1)
