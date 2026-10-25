"""6.36 Software Builder / Code mode: every ms_ws_* tool end-to-end in a temp folder."""
import json, os, sys, tempfile, threading, http.server, socketserver
from pathlib import Path
RT = Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RT))
import software_workspace as W  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="ms-ws636-"))
W.STATE_FILE = tmp / "state.json"
root = tmp / "proj"; root.mkdir()
fails = []
def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))
    if not cond: fails.append(name)
def call(n, a=None):
    r = W.call_tool(n, a or {})
    t = r["text"]
    try: return json.loads(t)
    except Exception: return t

check("disabled by default", call("ms_ws_status").get("ok") is False)
cfg = call("ms_ws_configure", {"enabled": True, "root": str(root), "allow_run": True, "mode": "code"})
check("configure code mode", cfg["ok"] and cfg["mode"] == "code")
st = call("ms_ws_status")
check("status reports mode + git + next", st["mode"] == "code" and "git" in st and "next" in st)

w = call("ms_ws_write", {"path": "src/app.py", "content": "def add(a, b):\n    return a + b\n\n\nclass Calc:\n    def mul(self, a, b):\n        return a * b\n"})
check("write creates file", w["ok"] and w["created"])
(root / "win.txt").write_bytes(b"alpha\r\nbeta  \r\ngamma\r\n")
e = call("ms_ws_edit", {"path": "win.txt", "edits": [{"old_string": "beta\ngamma", "new_string": "BETA\nGAMMA"}]})
check("edit tolerates CRLF + trailing spaces", e.get("ok") and (root / "win.txt").read_bytes() == b"alpha\r\nBETA\r\nGAMMA\r\n", (e, (root / "win.txt").read_bytes()))
e = call("ms_ws_edit", {"path": "src/app.py", "edits": [{"old_string": "return a+b", "new_string": "x"}]})
check("edit miss changes nothing + gives hint", e["ok"] is False and "closest_lines" in e)
e = call("ms_ws_edit", {"path": "src/app.py", "edits": [{"start_line": 2, "end_line": 2, "new_string": "    return int(a) + int(b)"}], "dry_run": True})
check("line-range dry run shows diff", e["dry_run"] and "+    return int(a) + int(b)" in e["diff"] and "int(a)" not in (root / "src/app.py").read_text())
e = call("ms_ws_edit", {"path": "src/app.py", "edits": [{"start_line": 2, "end_line": 2, "new_string": "    return int(a) + int(b)"}]})
check("line-range edit applies", "return int(a) + int(b)\n\n" in (root / "src/app.py").read_text())
e = call("ms_ws_edit", {"path": "src/app.py", "edits": {"old_string": "class Calc:", "new_string": "class Calculator:"}})
check("edits as single object tolerated", e.get("ok") and "class Calculator:" in (root / "src/app.py").read_text())
o = call("ms_ws_outline", {"path": "src/app.py"})
check("outline finds def/class", "def add" in o and "class Calculator" in o and "def mul" in o, o)
patch = """--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
+# header
 def add(a, b):
     return int(a) + int(b)
 
--- /dev/null
+++ b/README.md
@@ -0,0 +1,2 @@
+# Demo
+hello
"""
pd = call("ms_ws_patch", {"patch": patch, "dry_run": True})
check("patch dry-run validates", pd["ok"] and len(pd["files"]) == 2 and not (root / "README.md").exists())
pr = call("ms_ws_patch", {"patch": patch})
check("patch applies multi-file + new file", pr["ok"] and (root / "src/app.py").read_text().startswith("# header\n") and (root / "README.md").read_text() == "# Demo\nhello\n")
bad = call("ms_ws_patch", {"patch": "--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-nope\n+x\n"})
check("bad hunk is all-or-nothing", bad["ok"] is False)
g = call("ms_ws_glob", {"pattern": "**/*.py"})
check("glob finds python files", g["files"] == ["src/app.py"], g)
rm = call("ms_ws_read_many", {"paths": ["src/app.py", "README.md", "missing.txt"]})
check("read_many reads several + reports missing", "=== src/app.py" in rm and "=== README.md" in rm and "ERROR" in rm)
srch = call("ms_ws_search", {"query": "INT(A)", "context": 1})
check("search case-insensitive with context", "src/app.py:3:" in srch and "1 matches" in srch, srch)
rp = call("ms_ws_replace", {"query": "Calculator", "replacement": "Calc2", "glob": "*.py"})
check("replace defaults to dry run", rp["dry_run"] and rp["replacements"] == 1 and "Calculator" in (root / "src/app.py").read_text())
rp = call("ms_ws_replace", {"query": "Calculator", "replacement": "Calc2", "glob": "*.py", "dry_run": False})
check("replace applies", "class Calc2" in (root / "src/app.py").read_text())
u = call("ms_ws_undo")
check("undo reverts last change", u["ok"] and "class Calculator" in (root / "src/app.py").read_text(), u)
u = call("ms_ws_undo", {"path": "README.md"})
check("undo of a created file removes it", u["ok"] and not (root / "README.md").exists(), u)
lst = call("ms_ws_undo", {"action": "list"})
check("undo list", lst["ok"] and len(lst["changes"]) >= 3)
d = call("ms_ws_diff")
check("diff without git uses journal", isinstance(d, str) and "src/app.py" in d)
if __import__("shutil").which("git"):
    call("ms_ws_git", {"action": "init"})
    os.system(f'cd "{root}" && git config user.email t@t && git config user.name t')
    call("ms_ws_git", {"action": "add"})
    c = call("ms_ws_git", {"action": "commit", "message": "init $(echo pwned) `id`"})
    lg = call("ms_ws_git", {"action": "log"})
    check("git commit is injection-safe", c["ok"] and "$(echo pwned)" in lg["stdout"], (c, lg))
    (root / "src/app.py").write_text("changed\n")
    check("git diff", "changed" in call("ms_ws_diff"))
    check("git status read-only works", call("ms_ws_git", {"action": "status"})["ok"])
pl = call("ms_ws_plan", {"action": "set", "items": [{"text": "write code"}, {"text": "test"}]})
pl = call("ms_ws_plan", {"action": "update", "items": [{"id": 1, "status": "done", "note": "ok"}]})
check("plan set/update", "Plan 1/2 done" in pl and "[x] 1. write code" in pl, pl)
(root / "package.json").write_text(json.dumps({"name": "x", "scripts": {"test": "node -e \"process.exit(0)\"", "lint": "node -e \"console.error('error: bad');process.exit(1)\""}}))
det = call("ms_ws_build", {"step": "detect"})
node = next(k for k in det["project"] if k["kind"] == "node")
check("node recipes include lint", node["lint"] == "npm run lint" and node["test"] == "npm test")
if __import__("shutil").which("npm"):
    ck = call("ms_ws_check", {"steps": ["lint", "test"]})
    steps = {x["step"]: x for x in ck["steps"] if x["kind"] == "node"}
    check("check reports lint fail + test pass", ck["ok"] is False and steps["lint"]["ok"] is False and steps["test"]["ok"] is True, ck)
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"hi":1}')
    def log_message(self, *a): pass
srv = socketserver.TCPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
h = call("ms_ws_http", {"url": f"http://127.0.0.1:{srv.server_address[1]}/x"})
check("http to localhost", h["ok"] and h["status"] == 200 and '"hi"' in h["body"])
check("http to remote refused", call("ms_ws_http", {"url": "https://example.com"})["ok"] is False)
srv.shutdown()
r = call("ms_ws_run", {"command": "echo $FOO%FOO%", "env": {"FOO": "bar"}})
check("run passes env", "bar" in r["stdout"])
bgp = call("ms_ws_run", {"command": "sleep 30", "background": True})
stp = call("ms_ws_process", {"action": "stop", "id": bgp["id"]})
check("background stop kills tree", stp["running"] is False)
check("escape blocked", call("ms_ws_read", {"path": "../state.json"})["ok"] is False)
check("missing param explained", "missing required parameter" in call("ms_ws_read", {})["error"])
call("ms_ws_configure", {"allow_run": False})
check("git write gated when commands off", call("ms_ws_git", {"action": "commit", "message": "x"})["ok"] is False and call("ms_ws_git", {"action": "status"}).get("ok") is not False)
check("check gated when commands off", call("ms_ws_check")["ok"] is False)
import schema_perfect as SP
issues = [t["name"] for t in W.TOOLS if SP.perfect(t["inputSchema"], t["name"])[1]]
check("every ms_ws schema is already perfect (no normaliser fixes needed)", not issues, issues)
undoc = [f'{t["name"]}.{k}' for t in W.TOOLS for k, v in t["inputSchema"]["properties"].items() if not v.get("description")]
check("every ms_ws parameter is documented", not undoc, undoc)
print("FAILED:" if fails else "ALL PASS", fails)
sys.exit(1 if fails else 0)
