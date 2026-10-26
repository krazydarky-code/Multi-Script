#!/usr/bin/env python3
"""macOS / Linux setup + start scripts, run for real in an isolated copy with a fake $HOME."""
import json, os, shutil, signal, socket, stat, subprocess, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
failed = 0
def check(name, cond, detail=""):
    global failed
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {str(detail)[-700:]}"))
    if not cond: failed += 1

SCRIPTS = ["Setup.sh", "Start.sh", "MacOS_Setup.command", "MacOS_Start.command", "runtime/unix_env.sh", "Linux_Setup.sh", "Linux_Start.sh"]
# Windows cannot represent the POSIX executable bit: os.stat() there reports
# st_mode 0o100666 for every regular file no matter what its real mode is, so
# this check fails spuriously on a Windows development machine while passing on
# the Linux/macOS runners. Skip it ONLY on Windows - it stays strict everywhere
# the bit is real, which is where CI depends on it.
CHECK_EXEC_BIT = os.name != "nt"
BASH=shutil.which("bash")
if not BASH and os.name=="nt":
    candidate=os.path.join(os.environ.get("ProgramFiles",r"C:\Program Files"),"Git","bin","bash.exe")
    if os.path.isfile(candidate):BASH=candidate
for f in SCRIPTS:
    p = os.path.join(ROOT, f); data = open(p, "rb").read()
    check(f"{f}: LF line endings + bash shebang", b"\r" not in data and (f.endswith("unix_env.sh") or data.startswith(b"#!/")))
    if BASH:check(f"{f}: bash syntax",subprocess.run([BASH,"-n",p]).returncode==0)
    else:print(f"SKIP {f}: bash syntax checker unavailable")
    if not f.endswith("unix_env.sh") and CHECK_EXEC_BIT:
        check(f"{f}: executable bit set", os.stat(p).st_mode & stat.S_IXUSR)
check("Windows scripts keep CRLF", all(b"\r\n" in open(os.path.join(ROOT, f), "rb").read() for f in ("Setup.bat", "Start.bat")))
check("scripts avoid bash-4-only features (macOS ships bash 3.2)",
      not any(x in open(os.path.join(ROOT, f)).read() for f in SCRIPTS for x in ("declare -A", "mapfile", "readarray", ",,}", "^^}")))
if shutil.which("shellcheck"):
    check("shellcheck clean (errors)", subprocess.run(["shellcheck", "-S", "error"] + [os.path.join(ROOT, f) for f in SCRIPTS]).returncode == 0)

# The static checks above prove the scripts are well-formed on ANY machine. The
# integration section below actually EXECUTES Setup.sh / Start.sh in an isolated
# copy with a fake $HOME, registers a native-messaging host and signals a process
# group. None of that is representable on Windows: there is no bash Setup.sh, and
# os.killpg / S_IXUSR / start_new_session semantics do not exist there. Skipping
# here keeps the Windows dev run green for the RIGHT reason instead of reporting a
# product failure on a platform the scripts do not target. POSIX (Linux + macOS)
# stays fully strict - that is where this gate earns its keep.
if os.name == "nt":
    print("PASS unix scripts: static checks done; integration section skipped on Windows (POSIX-only)")
    print("0 failed" if failed == 0 else f"{failed} failed")
    sys.exit(1 if failed else 0)

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
def listening(port):
    try: socket.create_connection(("127.0.0.1", port), 0.4).close(); return True
    except OSError: return False

work = tempfile.mkdtemp(prefix="ms-unix-")
proj = os.path.join(work, "Multi Script")           # a space in the path on purpose
shutil.copytree(ROOT, proj, ignore=shutil.ignore_patterns("__pycache__", "logs", ".git", "node_modules", "*.pid", ".venv", "native_host.sh", "com.multiscript.bridge.json", "engine-prefs.json"))
home = os.path.join(work, "home"); os.makedirs(os.path.join(home, ".config", "google-chrome")); os.makedirs(os.path.join(home, ".config", "BraveSoftware", "Brave-Browser"))
os.makedirs(os.path.join(home, ".var", "app", "com.google.Chrome"))             # a sandboxed browser too
port = free_port(); 
while True:
    plug = port + 1
    if not listening(plug): break
    port = free_port()
env = dict(os.environ, HOME=home, XDG_CONFIG_HOME=os.path.join(home, ".config"), XDG_DATA_HOME=os.path.join(home, ".local", "share"),
           ZS_BRIDGE_PORT=str(port), ZS_ALLOW_TEMP_FOLDER="1", PATH=os.environ["PATH"])
env.pop("ZS_STUDIO_MCP_PATH", None)
def sh(args, timeout=150, **kw):
    return subprocess.run(["bash"] + args, cwd=proj, env=dict(env, **kw.pop("env", {})), capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, **kw)
def stop_bridge():
    try:
        sys.path.insert(0, os.path.join(proj, "runtime"))
        import importlib, native_host as nh
        importlib.reload(nh); nh.cmd_stop({"wait": 10})
    except Exception as e:
        print("stop error", e)

try:
    # 1) Setup refuses a temporary folder unless explicitly allowed
    r = subprocess.run(["bash", "Setup.sh", "--no-pause"], cwd=proj, env={k: v for k, v in env.items() if k != "ZS_ALLOW_TEMP_FOLDER"}, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    check("Setup.sh refuses a temporary/zipped folder", r.returncode == 1 and "temporary" in r.stdout, r.stdout + r.stderr)

    # 2) real setup
    r = sh(["Setup.sh", "--no-pause"])
    out = r.stdout + r.stderr
    check("Setup.sh exits 0", r.returncode == 0, out)
    check("Setup.sh finds Python and the websockets dependency", "ok Python:" in out and ("websockets" in out), out)
    nm = os.path.join(home, ".config", "google-chrome", "NativeMessagingHosts", "com.multiscript.bridge.json")
    check("registered for the installed Chrome (config dir)", os.path.isfile(nm), out)
    check("registered for Brave", os.path.isfile(os.path.join(home, ".config", "BraveSoftware", "Brave-Browser", "NativeMessagingHosts", "com.multiscript.bridge.json")))
    # CI can have Edge installed without a profile in this isolated HOME. The
    # installer intentionally supports that case as well as existing profiles.
    edge_present = (os.path.isdir("/Applications/Microsoft Edge.app") or
                    os.path.isdir(os.path.join(home, "Applications", "Microsoft Edge.app"))) if sys.platform == "darwin" else any(
                        shutil.which(command, path=env["PATH"]) for command in ("microsoft-edge", "microsoft-edge-stable"))
    edge_manifest = os.path.join(home, "Library", "Application Support", "Microsoft Edge", "NativeMessagingHosts", "com.multiscript.bridge.json") if sys.platform == "darwin" else os.path.join(
        home, ".config", "microsoft-edge", "NativeMessagingHosts", "com.multiscript.bridge.json")
    check("Edge registration matches the installed browser, including an unused profile", os.path.isfile(edge_manifest) == edge_present)
    man = json.load(open(nm)) if os.path.isfile(nm) else {}
    check("manifest points at this folder's launcher and the pinned extension id",
          man.get("path", "").startswith(proj) and man.get("path", "").endswith("native_host.sh") and
          any(o.startswith("chrome-extension://kdflpgjnhcognilmhabghnceaabblbcb") for o in man.get("allowed_origins", [])), man)
    check("launcher is executable and quotes the path with a space", os.access(man.get("path", "/nonexistent"), os.X_OK) and '"%s' % proj in open(man["path"]).read())
    check("Flatpak/Snap browser is reported as unable to launch the host", "sandboxed" in out.lower() and "Start.sh" in out, out)
    check("bridge was started and verified", "is running on port %d" % port in out, out)
    check("bridge answers on the port", listening(port))
    desk = os.path.join(home, ".local", "share", "applications", "multi-script-bridge.desktop")
    if sys.platform.startswith("linux"):
        d = open(desk).read() if os.path.isfile(desk) else ""
        check("Linux application-menu entry written (quoted path)", "Terminal=true" in d and 'Start.sh"' in d and proj in d, d)
    st = subprocess.run([sys.executable, "runtime/bridge_status.py", "--quiet"], cwd=proj, env=env).returncode
    check("bridge_status reports the current bridge (exit 0)", st == 0, st)

    # 3) re-running Setup with --keep-running leaves the bridge alone; plain re-run replaces it
    r = sh(["Setup.sh", "--no-pause", "--keep-running"])
    check("Setup.sh --keep-running is idempotent", r.returncode == 0 and "already running" in (r.stdout + r.stderr), r.stdout + r.stderr)
    r = sh(["Setup.sh", "--no-pause"])
    check("Setup.sh re-run succeeds", r.returncode == 0 and listening(port), r.stdout + r.stderr)

    # 4) the native host answers like a browser would (self test inside Setup passes)
    check("launcher self-test passed", "launcher answers" in out, out)

    # 5) uninstall
    stop_bridge()
    r = sh(["Setup.sh", "--no-pause", "--uninstall"])
    check("Setup.sh --uninstall removes the registrations", r.returncode == 0 and not os.path.exists(nm) and not os.path.exists(desk), r.stdout + r.stderr)

    # 6) Start.sh runs the bridge in the foreground; --yes replaces nothing when port is free
    p = subprocess.Popen(["bash", "Start.sh", "--no-pause", "--yes"], cwd=proj, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    t0 = time.time()
    while time.time() - t0 < 60 and not listening(port) and p.poll() is None: time.sleep(0.5)
    check("Start.sh brings the bridge up", listening(port), p.stdout.read() if p.poll() is not None else "")
    r2 = sh(["Start.sh", "--no-pause"], timeout=60)     # second copy, not a tty -> must not hang, must not kill the first
    check("a second Start.sh does not hang or kill the running bridge", listening(port), r2.stdout)
    os.killpg(p.pid, signal.SIGTERM)
    try: p.wait(15)
    except subprocess.TimeoutExpired: os.killpg(p.pid, signal.SIGKILL)
    time.sleep(1)
    check("Ctrl+C / SIGTERM stops the bridge", not listening(port))

    # 7) wrappers
    for w in ("MacOS_Setup.command", "MacOS_Start.command"):
        check(f"{w} delegates to the shared script", "exec bash ./%s" % w.replace("MacOS_", "").replace(".command", ".sh") in open(os.path.join(proj, w)).read())

    # 8) too-old Python -> clear hint, non-zero exit, nothing half-installed
    fake = os.path.join(work, "fakebin"); os.makedirs(fake)
    for name in ("python3", "python"):
        open(os.path.join(fake, name), "w").write("#!/bin/sh\nexit 1\n"); os.chmod(os.path.join(fake, name), 0o755)
    need = ["bash", "sh", "uname", "sed", "mktemp", "dirname", "readlink", "rm", "mkdir", "chmod", "date", "cat", "printf", "tail", "tr", "xattr"]
    minbin = os.path.join(work, "minbin"); os.makedirs(minbin)
    for n in need:
        w = shutil.which(n)
        if w: os.symlink(w, os.path.join(minbin, n))
    r = subprocess.run(["bash", "Setup.sh", "--no-pause"], cwd=proj, env=dict(env, PATH=fake + ":" + minbin), capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    check("no usable Python -> exit 1 with install instructions", r.returncode == 1 and "Python 3.9 or newer is required" in r.stdout, r.stdout + r.stderr)
    check("no half-registration after the failure", not os.path.exists(nm))

    # 9) PEP 668 / pip-less system python -> private venv fallback
    pyreal = shutil.which("python3")
    shim = os.path.join(work, "shim"); os.makedirs(shim)
    open(os.path.join(shim, "python3"), "w").write(
        "#!/bin/sh\n"
        'case "$*" in\n'
        '  *"import websockets"*) exec "%s" -c \'import sys; sys.exit(1)\' ;;\n'
        '  *"pip install --user"*) echo "error: externally-managed-environment" >&2; exit 1 ;;\n'
        'esac\nexec "%s" "$@"\n' % (pyreal, pyreal))
    os.chmod(os.path.join(shim, "python3"), 0o755)
    proj2 = os.path.join(work, "proj2"); shutil.copytree(proj, proj2, ignore=shutil.ignore_patterns("__pycache__", "logs", ".venv"))
    envs = dict(env, PATH=shim + ":" + minbin + ":" + os.path.dirname(pyreal), ZS_BRIDGE_PORT=str(free_port()))
    script = ('. runtime/unix_env.sh; MS_ROOT="$PWD"; MS_LOG=t.log; mkdir -p logs; ms_find_python || exit 9; '
              'ms_ensure_websockets || exit 8; echo "PY=$PY"; "$PY" -c "import websockets;print(websockets.__version__)"')
    r = subprocess.run(["bash", "-c", script], cwd=proj2, env=envs, capture_output=True, text=True, timeout=200, stdin=subprocess.DEVNULL)
    if r.returncode == 8 and "No matching distribution" in (r.stdout + r.stderr):
        print("SKIP venv fallback (no network)")
    else:
        check("externally-managed Python -> websockets installed into a private .venv", r.returncode == 0 and "/.venv/bin/python" in r.stdout, r.stdout + r.stderr)
finally:
    stop_bridge()
    for line in os.popen("ps -eo pid=,args=").read().splitlines():
        if work in line and "bridge.py" in line:
            try: os.kill(int(line.split()[0]), signal.SIGKILL)
            except Exception: pass
    shutil.rmtree(work, ignore_errors=True)

print(f"\n{failed} failure(s)")
sys.exit(1 if failed else 0)
