# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional LIVE harnesses for the engine toolkit tests. Every helper returns None when its
engine binary is not available, so tests SKIP instead of failing on a plain machine.

  BLENDER_PY  python with the `bpy` wheel   (default /tmp/bpyenv/bin/python, or env)
  GODOT_BIN   a Godot 4 editor binary       (default /tmp/tools/Godot_v4.4.1-stable_linux.x86_64)
  LUAU_BIN    dir with luau, luau-analyze   (default /tmp/tools)
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "runtime"))
import engine_toolkit as T  # noqa: E402


def _first(*c):
    for p in c:
        if p and os.path.isfile(p):
            return p
    return None


def blender_python():
    return _first(os.environ.get("BLENDER_PY"), "/tmp/bpyenv/bin/python")


def godot_bin():
    return _first(os.environ.get("GODOT_BIN"), "/tmp/tools/Godot_v4.4.1-stable_linux.x86_64", shutil.which("godot"))


def luau_dir():
    d = os.environ.get("LUAU_BIN") or "/tmp/tools"
    return d if os.path.isfile(os.path.join(d, "luau-analyze")) else None


class LiveBlender(T.Ctx):
    """A Ctx whose 'blender' server is a real headless Blender (bpy)."""

    def __init__(self):
        py = blender_python()
        if not py:
            raise RuntimeError("no bpy python")
        self.proc = subprocess.Popen([py, os.path.join(HERE, "bpy_worker.py")], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        ready = json.loads(self.proc.stdout.readline())
        self.version = ready.get("version")
        self.codes = []

    def advertised(self, server):
        return {"execute_blender_code", "get_scene_info", "get_object_info"} if server == "blender" else None

    def call(self, server, tool, arguments, timeout=120):
        code = arguments["code"]
        self.codes.append(code)
        self.proc.stdin.write(json.dumps({"code": code}) + "\n")
        self.proc.stdin.flush()
        reply = json.loads(self.proc.stdout.readline())
        return {"text": reply["out"] + (("\nTraceback\n" + reply["err"]) if reply["err"] else ""), "images": []}

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


def luau_compile(code):
    """(ok, message) from the real Luau compiler (syntax) - None if luau is missing."""
    d = luau_dir()
    if not d:
        return None
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".luau", delete=False, encoding="utf-8") as fh:
        fh.write(code)
        path = fh.name
    try:
        r = subprocess.run([os.path.join(d, "luau-compile"), "--text", path], capture_output=True, text=True, timeout=30)
        return r.returncode == 0, (r.stderr or r.stdout)[-400:]
    finally:
        os.unlink(path)


_VALIDATE = """extends SceneTree
func _init():
\tvar out := {}
\tfor p in @@PATHS@@:
\t\tvar r = load(p)
\t\tif r == null:
\t\t\tout[p] = "LOAD_FAILED"
\t\t\tcontinue
\t\tif r is PackedScene:
\t\t\tvar n = r.instantiate()
\t\t\tif n == null:
\t\t\t\tout[p] = "INSTANTIATE_FAILED"
\t\t\t\tcontinue
\t\t\tif @@READY@@:
\t\t\t\troot.add_child(n)
\t\t\tvar counts := {}
\t\t\tvar stack = [n]
\t\t\tvar total := 0
\t\t\twhile stack.size() > 0:
\t\t\t\tvar c = stack.pop_back()
\t\t\t\ttotal += 1
\t\t\t\tcounts[c.get_class()] = int(counts.get(c.get_class(), 0)) + 1
\t\t\t\tfor ch in c.get_children():
\t\t\t\t\tstack.append(ch)
\t\t\tout[p] = {"nodes": total, "classes": counts, "root": n.get_class()}
\t\t\tn.free()
\t\telse:
\t\t\tout[p] = {"resource": r.get_class()}
\tprint("MS_VALIDATE:" + JSON.stringify(out))
\tquit(0)
"""


def godot_validate(project, res_paths, timeout=120, ready=False):
    """Load every res:// path with a real headless Godot. Returns ({path: info}, [error lines]) or None if Godot is missing."""
    exe = godot_bin()
    if not exe:
        return None
    import json as _json
    import subprocess as _sp
    import tempfile as _tf
    d = _tf.mkdtemp(prefix="ms_val_")
    try:
        if not os.path.isdir(os.path.join(project, ".godot", "imported")):
            _sp.run([exe, "--headless", "--path", project, "--import"], capture_output=True, text=True, timeout=timeout)
        sp = os.path.join(d, "v.gd")
        open(sp, "w", encoding="utf-8", newline="\n").write(_VALIDATE.replace("@@PATHS@@", _json.dumps(list(res_paths))).replace("@@READY@@", "true" if ready else "false"))
        r = _sp.run([exe, "--headless", "--path", project, "--script", sp], capture_output=True, text=True, timeout=timeout)
        txt = (r.stdout or "") + "\n" + (r.stderr or "")
        info = {}
        for ln in txt.splitlines():
            if ln.startswith("MS_VALIDATE:"):
                info = _json.loads(ln[len("MS_VALIDATE:"):])
        errs = [ln for ln in txt.splitlines() if ("ERROR" in ln or "Parse Error" in ln) and "Failed to load script" not in ln or "Failed to load script" in ln]
        return info, errs
    finally:
        import shutil as _sh
        _sh.rmtree(d, ignore_errors=True)


def godot_check_scripts(project, res_paths, timeout=60):
    """--check-only parse of each GDScript. Returns [(path, output)] for failures, or None if Godot is missing."""
    exe = godot_bin()
    if not exe:
        return None
    import subprocess as _sp
    bad = []
    for rp in res_paths:
        r = _sp.run([exe, "--headless", "--path", project, "--check-only", "--script", rp], capture_output=True, text=True, timeout=timeout)
        txt = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0 or "SCRIPT ERROR" in txt or "Parse Error" in txt:
            bad.append((rp, txt[-500:]))
    return bad
