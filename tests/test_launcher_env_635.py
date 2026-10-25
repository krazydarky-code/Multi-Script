"""6.35: launcher helpers - realpath shim for uv shims on old macOS, EX_CONFIG,
signal exit codes, and the bridge's needs-setup back-off."""
import os, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import launcher_env as le

assert le.EX_CONFIG == 78
assert le.exit_code(-15) == 143 and le.exit_code(0) == 0 and le.exit_code(None) == 1
if os.name != "nt":
    with tempfile.TemporaryDirectory() as d:
        os.environ["XDG_CACHE_HOME"] = d
        env = le.ensure_realpath({"PATH": "/nonexistent"}, which=lambda *a, **k: None)
        shim = Path(env["PATH"].split(os.pathsep)[0]) / "realpath"
        assert shim.is_file() and os.access(shim, os.X_OK)
        target = Path(d) / "a" / "b"; target.mkdir(parents=True)
        link = Path(d) / "link"; link.symlink_to(target)
        out = subprocess.run([str(shim), str(link)], capture_output=True, text=True).stdout.strip()
        assert out == str(target.resolve()), out
        # uv's trampoline shape: exec "$(dirname -- "$(realpath -- "$0")")"/python
        out2 = subprocess.run([str(shim), "--", str(link)], capture_output=True, text=True).stdout.strip()
        assert out2 == str(target.resolve()), out2
    # A system realpath is left alone.
    env = le.ensure_realpath({"PATH": "/usr/bin"}, which=lambda *a, **k: "/usr/bin/realpath")
    assert env["PATH"] == "/usr/bin"
src = (ROOT / "runtime" / "bridge.py").read_text(encoding="utf-8")
assert "def _needs_setup(client)" in src and "needs setup:" in src
assert "except (OSError, ValueError):" in src  # console errors can't break restarts
for name in ("launch_blender_mcp.py", "launch_unity_mcp.py", "launch_godot_mcp.py", "launch_studio_mcp.py"):
    s = (ROOT / "runtime" / name).read_text(encoding="utf-8")
    assert "EX_CONFIG" in s and "exit_code(" in s, name
for name in ("launch_blender_mcp.py", "launch_unity_mcp.py"):
    s = (ROOT / "runtime" / name).read_text(encoding="utf-8")
    assert "env=child_env()" in s and "cwd=child_cwd()" in s, name
print("PASS launcher env: realpath shim, EX_CONFIG, signal exit codes, needs-setup back-off")
