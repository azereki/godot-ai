#!/usr/bin/env python3
r"""Serve the MCP dev server from *this worktree's* ``src/godot_ai`` (cross-platform).

A non-bash companion to ``script/serve-this-worktree`` so the worktree dev-server
flow works on Windows too (no ``bash``/``lsof`` dependency). It resolves this
worktree's ``src/``, the root repo's shared ``.venv`` interpreter (``bin/python``
on POSIX, ``Scripts\python.exe`` on Windows), frees the target port if a server
is already squatting on it, prepends ``src/`` to ``PYTHONPATH`` and execs
``python -m godot_ai --transport streamable-http --port <p> --reload``.

Extra args pass straight through to the module, so a non-default WebSocket port
works too::

    python script/serve-this-worktree.py --port 18130 --ws-port 19630

See issue #509.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make script/ importable so the shared dev-env helpers resolve regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _dev_env import (  # noqa: E402
    extract_port,
    find_venv_python,
    free_port,
    worktree_root,
    worktree_src,
)


def main(argv: list[str]) -> int:
    worktree = worktree_root()
    src = worktree_src(worktree)
    if not src.is_dir():
        print(f"error: {src} not found", file=sys.stderr)
        return 1

    venv_py = find_venv_python(worktree)
    if venv_py is None:
        print(
            "error: project .venv interpreter not found — run script/setup-dev "
            "(or script/setup-dev.ps1) in the root repo first",
            file=sys.stderr,
        )
        return 1

    port, passthrough = extract_port(argv, default=8000)
    # Free the port so we replace any plugin-spawned server rather than stack on it.
    free_port(port)

    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(src) + (os.pathsep + existing if existing else "")

    print(f"Serving worktree: {worktree}")
    print(f"Using venv:       {venv_py}")
    print(f"PYTHONPATH:       {src}")

    cmd = [
        str(venv_py),
        "-m",
        "godot_ai",
        "--transport",
        "streamable-http",
        "--port",
        str(port),
        "--reload",
        *passthrough,
    ]
    os.execve(str(venv_py), cmd, env)
    return 0  # unreachable; execve replaces the process


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
