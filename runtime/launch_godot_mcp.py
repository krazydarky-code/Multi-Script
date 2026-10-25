"""Multi-Script Godot MCP launcher.

Starts the pinned Godot MCP server (``@coding-solo/godot-mcp``) over stdio for the
Multi-Script bridge.

Two things matter here and are easy to get wrong:

1. **stdout belongs to the MCP protocol.** A stdio MCP server speaks JSON-RPC on
   stdout, so this launcher must NEVER print anything there - a stray line
   corrupts the handshake and the bridge reports a dead server with no useful
   error. Every diagnostic below therefore goes to stderr only, and there is a
   regression test that asserts stdout stays empty.

2. **The Godot editor path.** The Godot MCP needs to know where the Godot binary
   is (``GODOT_PATH``). If the user has not set it, the server starts but every
   project call fails with an opaque error. So we look for the binary in the
   places Godot actually installs itself, set ``GODOT_PATH`` when we find it, and
   say clearly on stderr what we found or what to set when we do not.

Environment overrides:
  ZS_NPX_PATH            explicit path to npx (npm/npx not on PATH)
  ZS_GODOT_MCP_VERSION   pin a different @coding-solo/godot-mcp version
  ZS_GODOT_PATH          explicit Godot binary (wins over auto-detection)
  GODOT_PATH             the variable the server itself reads (also honoured)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Sibling module: the bridge launches us by path (so our directory is already on
# sys.path), but tests and tooling import us directly, where it is not.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_child_signals import forward_signals  # noqa: E402  (path inserted above)
from launcher_env import EX_CONFIG, child_cwd, child_env, exit_code  # noqa: E402

DEFAULT_VERSION = "0.1.1"
PACKAGE = "@coding-solo/godot-mcp"
MIN_NODE_MAJOR = 18


def log(msg):
    """Diagnostics go to stderr ONLY - stdout is the MCP JSON-RPC channel."""
    try:
        sys.stderr.write("[godot-mcp] %s\n" % msg)
        sys.stderr.flush()
    except Exception:
        pass


def find_npx(env=None, which=shutil.which):
    env = os.environ if env is None else env
    override = env.get("ZS_NPX_PATH")
    if override:
        p = Path(override).expanduser()
        if p.is_file():
            return str(p)
        log("ZS_NPX_PATH is set but is not a file: %s" % override)
    return which("npx")


def node_major(which=shutil.which, run=subprocess.run):
    """Major version of the Node on PATH, or 0 when it is missing/unreadable."""
    node = which("node")
    if not node:
        return 0
    try:
        out = run([node, "--version"], capture_output=True, text=True, timeout=8).stdout
        return int(re.search(r"\d+", out).group())
    except Exception:
        return 0


def godot_candidates(env=None, platform=None):
    """Places the Godot editor is normally installed, most specific first.

    A pure function of (env, platform) so it is unit-testable.
    """
    env = os.environ if env is None else env
    platform = platform or sys.platform
    out = []
    for key in ("ZS_GODOT_PATH", "GODOT_PATH", "GODOT4_PATH", "GODOT_BIN"):
        v = env.get(key)
        if v:
            out.append(v)
    if platform.startswith("win"):
        local = env.get("LOCALAPPDATA") or ""
        prog = env.get("PROGRAMFILES") or "C:\\Program Files"
        prog86 = env.get("PROGRAMFILES(X86)") or "C:\\Program Files (x86)"
        bases = [b for b in (local and Path(local) / "Programs" / "Godot", Path(prog) / "Godot", Path(prog86) / "Godot") if b]
        for base in bases:
            # Canonical names first (they are cheap and always reported, so the
            # "where we looked" list is stable even on a machine without Godot).
            out.append(str(base / "godot.exe"))
            out.append(str(base / "Godot.exe"))
            try:
                if Path(base).is_dir():
                    out += [str(p) for p in sorted(Path(base).glob("*.exe"))]
            except Exception:
                pass
        for base in [b for b in (local and Path(local) / "Programs", Path(prog), Path(prog86)) if b]:
            try:
                if Path(base).is_dir():
                    out += [str(p) for p in sorted(Path(base).glob("Godot*/*.exe"))]
            except Exception:
                pass
    elif platform == "darwin":
        out += [
            "/Applications/Godot.app/Contents/MacOS/Godot",
            "/Applications/Godot_mono.app/Contents/MacOS/Godot",
            str(Path.home() / "Applications" / "Godot.app" / "Contents" / "MacOS" / "Godot"),
            str(Path.home() / "Applications" / "Godot_mono.app" / "Contents" / "MacOS" / "Godot"),
            "/opt/homebrew/bin/godot", "/usr/local/bin/godot",
        ]
    else:
        out += [
            "/usr/bin/godot", "/usr/local/bin/godot", "/usr/bin/godot4",
            "/snap/bin/godot", "/var/lib/flatpak/exports/bin/org.godotengine.Godot",
            str(Path.home() / ".local" / "share" / "flatpak" / "exports" / "bin" / "org.godotengine.Godot"),
            "/usr/games/godot", "/opt/godot/godot", "/opt/Godot/Godot",
            str(Path.home() / ".local" / "bin" / "godot"),
            str(Path.home() / ".local" / "bin" / "godot4"),
        ]
        # AppImage / unpacked downloads people keep in ~/Applications, ~/bin or ~/Downloads.
        for folder in (Path.home() / "Applications", Path.home() / "bin", Path.home() / "Downloads", Path.home() / "Godot"):
            try:
                if folder.is_dir():
                    out += [str(p) for p in sorted(folder.glob("Godot*")) if p.is_file() and os.access(str(p), os.X_OK)]
                    out += [str(p) for p in sorted(folder.glob("Godot*/Godot*")) if p.is_file() and os.access(str(p), os.X_OK)]
            except Exception:
                pass
    return out


def find_godot(env=None, which=shutil.which, platform=None):
    """First usable Godot binary, or None. Never raises."""
    env = os.environ if env is None else env
    for cand in godot_candidates(env, platform):
        try:
            if Path(cand).expanduser().is_file():
                return str(Path(cand).expanduser())
        except Exception:
            continue
    try:
        return which("godot") or which("godot4")
    except Exception:
        return None


def build_command(npx, version, extra, platform=None):
    """The exact argv used to start the server. Pure, so it can be asserted."""
    cmd = [npx, "-y", "%s@%s" % (PACKAGE, version)] + list(extra)
    platform = platform or sys.platform
    if platform.startswith("win") and npx.lower().endswith((".cmd", ".bat")):
        cmd = ["cmd.exe", "/c"] + cmd
    return cmd


def main(argv=None, env=None, which=shutil.which, popen=subprocess.Popen):
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env

    npx = find_npx(env, which)
    if not npx:
        log("npx was not found. Install Node.js 18+ (which includes npm/npx), or set "
            "ZS_NPX_PATH to the full path of npx.cmd, then restart the bridge.")
        return EX_CONFIG

    major = node_major(which)
    if major and major < MIN_NODE_MAJOR:
        log("Node.js %d is too old - the Godot MCP needs %d+." % (major, MIN_NODE_MAJOR))
        return EX_CONFIG
    if not major:
        log("node was not found on PATH; starting anyway and letting npx report the problem.")

    # Tell the server where Godot is, unless the user already did. Without this the
    # server starts happily and then fails every project call with an opaque error.
    if not env.get("GODOT_PATH"):
        found = find_godot(env, which)
        if found:
            env["GODOT_PATH"] = found
            log("GODOT_PATH was not set - detected the Godot editor at: %s" % found)
        else:
            log("GODOT_PATH is not set and no Godot editor was found in the usual install "
                "locations. The server will start, but project commands will fail until you set "
                "GODOT_PATH in runtime/config.json -> mcpServers.godot.env.")

    version = env.get("ZS_GODOT_MCP_VERSION") or DEFAULT_VERSION
    cmd = build_command(npx, version, argv)
    log("starting %s@%s (argv passthrough: %s)" % (PACKAGE, version, argv or "none"))

    try:
        proc = popen(cmd, env=child_env(env))
    except FileNotFoundError:
        log("could not execute npx at %s. Check the path, or install Node.js 18+." % npx)
        return 1
    except Exception as e:
        log("could not start the Godot MCP server: %s" % e)
        return 1

    # Forward Ctrl+C - and, on macOS/Linux, the bare SIGTERM the bridge uses to
    # stop a server - to the child instead of orphaning it: a bridge restart that
    # leaves the old server holding the project is a confusing state to debug, and
    # the orphan keeps a lock on the project folder.
    forward_signals(proc)
    try:
        return exit_code(proc.wait())
    except KeyboardInterrupt:
        log("interrupted - stopping the Godot MCP server")
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
