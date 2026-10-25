# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared helpers for the MCP launchers (stdio servers started by the bridge).

* EX_CONFIG (78): the launcher's prerequisite is missing (npx, uvx, editor).
  The bridge treats this exit code as "needs setup" and stops hammering
  restarts; it only retries slowly or when the user asks.
* child_env(): makes uv/uvx console-script shims work on older macOS. uv's
  generated ``bin/<tool>`` trampolines run ``realpath`` (missing before macOS 13)
  and otherwise exec ``./python`` relative to the current directory, which is
  the "realpath: command not found ... runtime/python: No such file" failure.
  We put a tiny portable ``realpath`` on PATH for the child when none exists.
* exit_code(): signal deaths (-15) become 128+N (143) instead of 241.
"""
from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile

EX_CONFIG = 78

_REALPATH = """#!/bin/sh
# Multi-Script portable realpath (older macOS ships without one).
for a in "$@"; do
  case "$a" in --|-e|-m|-q|-s) continue;; esac
  exec "%s" -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$a"
done
"""


def shim_dir() -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    path = os.path.join(base, "multiscript", "shims")
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        path = os.path.join(tempfile.gettempdir(), "multiscript-shims")
        os.makedirs(path, exist_ok=True)
        return path


def ensure_realpath(env: dict, which=shutil.which) -> dict:
    """Return env with a working ``realpath`` on PATH (POSIX only)."""
    if sys.platform == "win32":
        return env
    if which("realpath", path=env.get("PATH")):
        return env
    d = shim_dir()
    target = os.path.join(d, "realpath")
    body = _REALPATH % (sys.executable or "/usr/bin/python3")
    try:
        old = open(target).read() if os.path.exists(target) else ""
        if old != body:
            with open(target, "w") as f:
                f.write(body)
        os.chmod(target, os.stat(target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        return env
    env = dict(env)
    env["PATH"] = d + os.pathsep + env.get("PATH", "")
    return env


def child_env(base=None) -> dict:
    env = dict(os.environ if base is None else base)
    return ensure_realpath(env)


def child_cwd() -> str:
    """A neutral working directory: never the runtime folder (see module doc)."""
    return os.path.expanduser("~")


def exit_code(rc):
    if rc is None:
        return 1
    return 128 - rc if rc < 0 else rc
