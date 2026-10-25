"""Godot launcher regression.

Covers the two failure modes that are invisible from the bridge side:
  1. the launcher writing to STDOUT (which corrupts the MCP JSON-RPC handshake and
     makes the server look dead with no error) - asserted by actually running the
     launcher against a fake npx;
  2. GODOT_PATH never being set, so the server starts and every project command
     fails with an opaque error - asserted on the pure detection helpers.
Also pins the version, the ZS_GODOT_MCP_VERSION override, the argv passthrough
and the child's exit-code passthrough.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("godot_launcher", ROOT / "runtime" / "launch_godot_mcp.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# ── Version pin + override ────────────────────────────────────────────────
assert m.DEFAULT_VERSION == "0.1.1", m.DEFAULT_VERSION
assert m.PACKAGE == "@coding-solo/godot-mcp", m.PACKAGE
assert m.MIN_NODE_MAJOR >= 18, m.MIN_NODE_MAJOR
cmd = m.build_command("npx", "0.1.1", [], platform="linux")
assert cmd == ["npx", "-y", "@coding-solo/godot-mcp@0.1.1"], cmd
# Windows .cmd shims must be wrapped so the shell builtin resolution works.
cmd_win = m.build_command("C:\\npm\\npx.cmd", "0.1.1", ["--x"], platform="win32")
assert cmd_win[:3] == ["cmd.exe", "/c", "C:\\npm\\npx.cmd"], cmd_win
assert cmd_win[-1] == "--x", cmd_win
# A real .exe npx must NOT be wrapped.
cmd_exe = m.build_command("C:\\node\\npx.exe", "0.1.1", [], platform="win32")
assert cmd_exe[0].endswith("npx.exe"), cmd_exe

# ── ZS_NPX_PATH override ──────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as d:
    fake = Path(d) / ("npx.cmd" if os.name == "nt" else "npx")
    fake.write_text("")
    assert m.find_npx({"ZS_NPX_PATH": str(fake)}) == str(fake)
    # A bogus override must fall through to PATH, not crash or return the bogus path.
    got = m.find_npx({"ZS_NPX_PATH": str(Path(d) / "nope")})
    assert got != str(Path(d) / "nope"), got

# ── Godot detection: explicit env wins, per-platform locations are listed ──
with tempfile.TemporaryDirectory() as d:
    g = Path(d) / ("Godot.exe" if os.name == "nt" else "godot")
    g.write_text("")
    assert m.find_godot({"GODOT_PATH": str(g)}) == str(g)
    assert m.find_godot({"ZS_GODOT_PATH": str(g)}) == str(g)
    assert m.find_godot({"GODOT4_PATH": str(g)}) == str(g)
    # A path that does not exist must be skipped, not returned.
    assert m.find_godot({"GODOT_PATH": str(Path(d) / "missing")}, which=lambda n: None) is None
    cands_win = m.godot_candidates({"LOCALAPPDATA": d}, platform="win32")
    assert any("Programs" in c for c in cands_win), cands_win
    cands_mac = m.godot_candidates({}, platform="darwin")
    assert any(c.endswith("Godot.app/Contents/MacOS/Godot") for c in cands_mac), cands_mac
    cands_lin = m.godot_candidates({}, platform="linux")
    assert "/usr/bin/godot" in cands_lin and any("flatpak" in c for c in cands_lin), cands_lin
    # Every candidate list must be a list of strings, never None (a None would
    # blow up Path() inside find_godot).
    for env, plat in (({}, "win32"), ({}, "darwin"), ({}, "linux"), ({}, "freebsd")):
        for c in m.godot_candidates(env, platform=plat):
            assert isinstance(c, str) and c, (env, plat, c)

# ── main(): missing npx fails cleanly, with a message on stderr ────────────
rc = m.main([], env={}, which=lambda n: None, popen=lambda *a, **k: None)
assert rc == 78, rc  # EX_CONFIG: prerequisite missing

# ── End-to-end through a fake npx: stdout stays EMPTY, args and exit code pass through ──
with tempfile.TemporaryDirectory() as d:
    if os.name == "nt":
        fake = Path(d) / "npx.cmd"
        fake.write_text("@echo off\r\necho FAKEARGS %* 1>&2\r\nexit /b 7\r\n")
    else:
        fake = Path(d) / "npx"
        fake.write_text('#!/bin/sh\necho "FAKEARGS $*" 1>&2\nexit 7\n')
        fake.chmod(0o755)
    env = dict(os.environ)
    env["ZS_NPX_PATH"] = str(fake)
    env["ZS_GODOT_MCP_VERSION"] = "9.9.9"
    env["GODOT_PATH"] = str(fake)  # pretend a Godot binary, so no detection log noise
    proc = subprocess.run(
        [sys.executable, str(ROOT / "runtime" / "launch_godot_mcp.py"), "--project", "/tmp/g"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert proc.returncode == 7, "exit code was not passed through: %r / %r" % (proc.returncode, proc.stderr)
    assert proc.stdout == "", "the launcher wrote to stdout, which corrupts the MCP handshake: %r" % proc.stdout
    assert "FAKEARGS" in proc.stderr, proc.stderr
    # The pinned override and the argv passthrough must both reach npx.
    assert "9.9.9" in proc.stderr, proc.stderr
    assert "--project" in proc.stderr, proc.stderr
    assert "argv passthrough: ['--project', '/tmp/g']" in proc.stderr, proc.stderr

print("PASS Godot launcher: version pin + override, .cmd wrapping, ZS_NPX_PATH, per-platform Godot "
      "auto-detection, clean failure without npx, exit-code and argv passthrough, and stdout kept "
      "empty for the MCP protocol")
