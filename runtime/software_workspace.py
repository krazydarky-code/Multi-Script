# SPDX-License-Identifier: GPL-3.0-or-later
"""software_workspace.py - Software Builder / Code mode workspace tools (6.36).

Two session modes share these tools: "build" (scaffold, compile and package a
new program) and "code" (a general coding agent on ANY local folder: read,
search, patch, refactor, test, git). Every write is backed up for ms_ws_undo.

Lets any provider model build, compile and package a real desktop / web / CLI
program on the user's machine, using the local bridge as the harness. Every
path is jailed inside ONE workspace root that the USER chose (native folder
picker, a typed path, or a fresh folder Multi-Script creates). Nothing here is
reachable unless the extension has enabled Software Builder for the session
(see ms_ws_configure, which the extension calls itself and refuses from models).

Design rules
  * Root jail: every path is resolved and must stay inside the workspace root.
  * Nothing silent: writes report bytes + line counts, edits report each hunk,
    commands report exit code, duration and head/tail of output.
  * Reversible: ms_ws_snapshot zips the project before risky work; restore puts
    it back. Deletes require confirm=true and never touch the root itself.
  * Commands are opt-in: ms_ws_run / ms_ws_build need allow_run (a settings
    toggle). Known machine-destroying commands are refused even then.
"""
import edition
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "workspace-state.json"
DEFAULT_PROJECTS_DIR = Path.home() / "Multi-Script Projects"
IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", "bin", "obj",
               "target", ".idea", ".vscode", ".ms_snapshots", ".next", ".cache", ".pytest_cache", ".mypy_cache"}
MAX_READ = 200_000
MAX_WRITE = 2_000_000
OUT_HEAD, OUT_TAIL = 6000, 6000

_lock = threading.Lock()
_procs = {}  # id -> {"proc", "cmd", "started", "log": Path}


# ── state ────────────────────────────────────────────────────────────────
def _load():
    try:
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return s if isinstance(s, dict) else {}
    except Exception:
        return {}


def _save(s):
    try:
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=2), encoding="utf-8")
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


def _out(obj):
    return {"text": json.dumps(obj, indent=2, ensure_ascii=False) if not isinstance(obj, str) else obj, "images": []}


def _err(msg, **extra):
    d = {"ok": False, "error": msg}
    d.update(extra)
    return _out(d)


def _root():
    s = _load()
    r = s.get("root")
    if not r:
        return None
    p = Path(r)
    return p if p.is_dir() else None


def _require_enabled():
    s = _load()
    if not s.get("enabled"):
        return "Software Builder is disabled. The user enables it in Multi-Script settings → Code & Build, then starts a 'Build software' session."
    if not _root():
        return "No workspace folder is selected. Call ms_ws_pick_folder (opens a folder picker on the user's PC) or ms_ws_create_project to make a new project folder."
    return None


def _safe(rel, must_exist=False):
    root = _root()
    if root is None:
        raise ValueError("no workspace root")
    rel = str(rel or ".").strip().replace("\\", "/")
    if rel.startswith("~"):
        raise ValueError("paths are relative to the workspace root; '~' is not allowed")
    p = Path(rel)
    full = (p if p.is_absolute() else root / p).resolve()
    rr = root.resolve()
    if full != rr and rr not in full.parents:
        raise ValueError(f"path '{rel}' escapes the workspace root {rr}")
    if must_exist and not full.exists():
        raise FileNotFoundError(f"'{rel}' does not exist in the workspace")
    return full


def _rel(p):
    root = _root().resolve()
    try:
        return str(Path(p).resolve().relative_to(root)).replace("\\", "/") or "."
    except Exception:
        return str(p)


def _clip(text):
    text = text or ""
    if len(text) <= OUT_HEAD + OUT_TAIL + 200:
        return text
    return text[:OUT_HEAD] + f"\n…[{len(text) - OUT_HEAD - OUT_TAIL} chars omitted]…\n" + text[-OUT_TAIL:]


# ── undo journal / diffs (6.36) ──────────────────────────────────────────
import difflib

UNDO_KEEP = 40


def _undo_dir():
    d = _root() / ".ms_snapshots" / "undo"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _journal_path():
    return _undo_dir() / "journal.json"


def _journal():
    try:
        j = json.loads(_journal_path().read_text(encoding="utf-8"))
        return j if isinstance(j, list) else []
    except Exception:
        return []


def _backup(p, op):
    """Remember the file's previous state (or absence) before a change."""
    try:
        j = _journal()
        entry = {"t": time.time(), "path": _rel(p), "op": op, "existed": p.exists() and p.is_file()}
        if entry["existed"]:
            if p.stat().st_size > MAX_WRITE * 2:
                return
            blob = _undo_dir() / f"{int(time.time() * 1000)}-{len(j)}.bak"
            shutil.copy2(p, blob)
            entry["blob"] = blob.name
        j.append(entry)
        for old in j[:-UNDO_KEEP]:
            if old.get("blob"):
                try:
                    (_undo_dir() / old["blob"]).unlink()
                except Exception:
                    pass
        _journal_path().write_text(json.dumps(j[-UNDO_KEEP:], indent=1), encoding="utf-8")
    except Exception:
        pass


def _diff(before, after, rel, ctx=2, limit=4000):
    d = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"a/{rel}", f"b/{rel}", n=ctx))
    return d if len(d) <= limit else d[:limit] + f"\n…[diff truncated, {len(d) - limit} more chars]"


def _read_text(p):
    raw = p.read_bytes()
    if b"\x00" in raw[:4096]:
        raise ValueError(f"'{_rel(p)}' is a binary file")
    return raw.decode("utf-8", errors="replace")


def _write_text(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _find_flex(text, old):
    """Locate `old` in `text`: exact, then CRLF-adapted, then trailing-whitespace
    tolerant line match. Returns (start, end, how) or None."""
    i = text.find(old)
    if i >= 0:
        return i, i + len(old), "exact"
    if "\r\n" in text and "\r\n" not in old and "\n" in old:
        o2 = old.replace("\n", "\r\n")
        i = text.find(o2)
        if i >= 0:
            return i, i + len(o2), "crlf"
    tl = text.splitlines(True)
    ol = [x.rstrip() for x in old.splitlines()]
    while ol and not ol[-1]:
        ol.pop()
    if not ol:
        return None
    n = len(ol)
    hits = []
    for k in range(len(tl) - n + 1):
        if all(tl[k + m].rstrip() == ol[m] for m in range(n)):
            hits.append(k)
            if len(hits) > 1:
                break
    if len(hits) != 1:
        stripped = [x.strip() for x in ol]
        hits = [k for k in range(len(tl) - n + 1) if all(tl[k + m].strip() == stripped[m] for m in range(n))][:2]
        if len(hits) != 1:
            return None
        how = "indent-insensitive"
    else:
        how = "whitespace-tolerant"
    k = hits[0]
    start = sum(len(x) for x in tl[:k])
    end = start + sum(len(x) for x in tl[k:k + n])
    if tl[k + n - 1].endswith("\n") and not old.endswith("\n"):
        end -= 2 if tl[k + n - 1].endswith("\r\n") else 1
    return start, end, how


def _adapt_eol(text, new):
    return new.replace("\r\n", "\n").replace("\n", "\r\n") if "\r\n" in text and "\r\n" not in new else new


def _apply_hunks(text, hunks):
    """Apply unified-diff hunks [(old_lines, new_lines)] with context matching."""
    lines = text.splitlines(True)
    eol = "\r\n" if "\r\n" in text else "\n"
    pos = 0
    for idx, (old, new) in enumerate(hunks):
        n = len(old)
        found = -1
        for strict in (True, False):
            for k in list(range(pos, len(lines) - n + 1)) + list(range(0, min(pos, max(0, len(lines) - n + 1)))):
                seg = lines[k:k + n]
                ok = all((a.rstrip("\r\n") == b) if strict else (a.strip() == b.strip()) for a, b in zip(seg, old))
                if ok:
                    found = k
                    break
            if found >= 0:
                break
        if found < 0 and n == 0:
            found = len(lines)
        if found < 0:
            raise ValueError(f"hunk {idx + 1} does not match the file (first context line: {old[0] if old else ''!r})")
        repl = [x + eol for x in new]
        if found + n == len(lines) and lines and not lines[-1].endswith(("\n", "\r")) and repl:
            repl[-1] = repl[-1].rstrip("\r\n")
        lines[found:found + n] = repl
        pos = found + len(repl)
    return "".join(lines)


def _parse_patch(patch):
    """Unified diff -> {path: {"hunks": [...], "new": bool, "delete": bool}}."""
    files, cur, hunk = {}, None, None
    rows = patch.replace("\r\n", "\n").split("\n")
    if rows and rows[-1] == "":
        rows.pop()
    for raw in rows:
        if raw.startswith("--- "):
            src = raw[4:].strip().split("\t")[0]
            cur = {"src": src, "hunks": []}
            continue
        if raw.startswith("+++ ") and cur is not None:
            dst = raw[4:].strip().split("\t")[0]
            path = dst if dst != "/dev/null" else cur["src"]
            path = re.sub(r"^[ab]/", "", path)
            cur.update(new=cur["src"] == "/dev/null", delete=dst == "/dev/null")
            files[path] = cur
            hunk = None
            continue
        if raw.startswith("@@") and cur is not None:
            hunk = ([], [])
            cur["hunks"].append(hunk)
            continue
        if hunk is None or raw.startswith("\\"):
            continue
        tag, body = (raw[:1], raw[1:]) if raw else (" ", "")
        if tag == " ":
            hunk[0].append(body); hunk[1].append(body)
        elif tag == "-":
            hunk[0].append(body)
        elif tag == "+":
            hunk[1].append(body)
    return files


OUTLINE = [
    (r"\.(py|pyw)$", r"^\s*(?:async\s+)?(def|class)\s+([A-Za-z_]\w*)"),
    (r"\.(js|jsx|mjs|cjs|ts|tsx)$", r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(function\*?|class|interface|type|enum|const|let)\s+([A-Za-z_$][\w$]*)(?:\s*[=:(<]|\s*\{|\s+extends|\s*$)"),
    (r"\.(go)$", r"^\s*(func|type)\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)"),
    (r"\.(rs)$", r"^\s*(?:pub(?:\([^)]*\))?\s+)?(fn|struct|enum|trait|impl|mod|type)\s+([A-Za-z_]\w*)"),
    (r"\.(cs|java|kt)$", r"^\s*(?:(?:public|private|protected|internal|static|sealed|abstract|partial|override|virtual|async|final|open|data)\s+)*(class|interface|struct|enum|record|void|fun|[A-Za-z_<>\[\],]+)\s+([A-Za-z_]\w*)\s*[({<:]"),
    (r"\.(c|cc|cpp|cxx|h|hpp)$", r"^\s*(?:static\s+|inline\s+|virtual\s+)*(class|struct|enum|[A-Za-z_][\w:<>*&\s]*?)\s+\**([A-Za-z_][\w:]*)\s*\([^;]*$"),
    (r"\.(gd)$", r"^\s*(func|class_name|class|signal|enum)\s+([A-Za-z_]\w*)"),
    (r"\.(lua|luau)$", r"^\s*(?:local\s+)?(function)\s+([A-Za-z_][\w.:]*)"),
    (r"\.(rb)$", r"^\s*(def|class|module)\s+([A-Za-z_][\w.:?!]*)"),
    (r"\.(php)$", r"^\s*(?:public|private|protected|static|abstract|final|\s)*(function|class|interface|trait)\s+([A-Za-z_]\w*)"),
    (r"\.(swift)$", r"^\s*(?:public\s+|private\s+|internal\s+|open\s+|static\s+)*(func|class|struct|enum|protocol|extension)\s+([A-Za-z_]\w*)"),
    (r"\.(md|markdown)$", r"^(#{1,4})\s+(.+)$"),
]


def _plan_path():
    return _root() / ".ms_snapshots" / "plan.json"


# ── toolchains ───────────────────────────────────────────────────────────
TOOLCHAINS = {
    "python": [sys.executable or "python", "--version"], "node": ["node", "--version"], "npm": ["npm", "--version"],
    "pnpm": ["pnpm", "--version"], "dotnet": ["dotnet", "--version"], "cargo": ["cargo", "--version"],
    "go": ["go", "version"], "gcc": ["gcc", "--version"], "g++": ["g++", "--version"], "clang": ["clang", "--version"],
    "cmake": ["cmake", "--version"], "make": ["make", "--version"], "java": ["java", "-version"], "git": ["git", "--version"],
    "pyinstaller": ["pyinstaller", "--version"], "msbuild": ["msbuild", "-version"],
}


def detect_toolchains():
    found = {}
    for name, cmd in TOOLCHAINS.items():
        exe = cmd[0] if os.path.isabs(cmd[0]) else shutil.which(cmd[0])
        if not exe:
            continue
        try:
            r = subprocess.run([exe] + cmd[1:], capture_output=True, text=True, timeout=8, **_nowin())
            line = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
            found[name] = line[0][:80] if line else "present"
        except Exception:
            found[name] = "present (version check failed)"
    return found


def _nowin():
    if os.name == "nt":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


# ── templates ────────────────────────────────────────────────────────────
def _tpl(name, title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "app"
    mod = slug.replace("-", "_")
    T = {
        "python-cli": {
            "README.md": f"# {title}\n\nRun: `python -m {mod}`\nTest: `python -m unittest`\n",
            f"{mod}/__init__.py": "__version__ = '0.1.0'\n",
            f"{mod}/__main__.py": f"import argparse\n\n\ndef main(argv=None):\n    p = argparse.ArgumentParser(prog='{slug}', description='{title}')\n    p.add_argument('name', nargs='?', default='world')\n    a = p.parse_args(argv)\n    print(f'Hello, {{a.name}}!')\n    return 0\n\n\nif __name__ == '__main__':\n    raise SystemExit(main())\n",
            "tests/test_main.py": f"import unittest\nfrom {mod}.__main__ import main\n\n\nclass T(unittest.TestCase):\n    def test_runs(self):\n        self.assertEqual(main(['x']), 0)\n\n\nif __name__ == '__main__':\n    unittest.main()\n",
            "pyproject.toml": f"[project]\nname = \"{slug}\"\nversion = \"0.1.0\"\nrequires-python = \">=3.9\"\n\n[project.scripts]\n{slug} = \"{mod}.__main__:main\"\n",
        },
        "python-gui": {
            "README.md": f"# {title}\n\nRun: `python app.py` (Tkinter, no installs). Package: `pyinstaller --onefile --windowed app.py`\n",
            "app.py": f"import tkinter as tk\nfrom tkinter import ttk\n\n\nclass App(tk.Tk):\n    def __init__(self):\n        super().__init__()\n        self.title('{title}')\n        self.geometry('480x320')\n        self.count = tk.IntVar(value=0)\n        f = ttk.Frame(self, padding=16)\n        f.pack(fill='both', expand=True)\n        ttk.Label(f, text='{title}', font=('Segoe UI', 16, 'bold')).pack(anchor='w')\n        ttk.Label(f, textvariable=self.count, font=('Segoe UI', 32)).pack(pady=20)\n        ttk.Button(f, text='Click', command=lambda: self.count.set(self.count.get() + 1)).pack()\n\n\nif __name__ == '__main__':\n    App().mainloop()\n",
        },
        "node-cli": {
            "README.md": f"# {title}\n\nRun: `node src/index.js` · Test: `npm test`\n",
            "package.json": json.dumps({"name": slug, "version": "0.1.0", "type": "module", "bin": {slug: "src/index.js"}, "scripts": {"start": "node src/index.js", "test": "node --test"}}, indent=2) + "\n",
            "src/index.js": "#!/usr/bin/env node\nexport function greet(name = 'world') { return `Hello, ${name}!`; }\nif (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith('index.js')) console.log(greet(process.argv[2]));\n",
            "test/index.test.js": "import test from 'node:test';\nimport assert from 'node:assert';\nimport { greet } from '../src/index.js';\ntest('greet', () => assert.equal(greet('a'), 'Hello, a!'));\n",
        },
        "web-static": {
            "README.md": f"# {title}\n\nOpen `index.html` in a browser, or run `python -m http.server 8000`.\n",
            "index.html": f"<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>{title}</title>\n<link rel=\"stylesheet\" href=\"style.css\">\n</head>\n<body>\n<main>\n<h1>{title}</h1>\n<button id=\"go\">Click me</button>\n<p id=\"out\">0</p>\n</main>\n<script src=\"app.js\"></script>\n</body>\n</html>\n",
            "style.css": ":root{color-scheme:dark;font-family:system-ui,sans-serif}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#111;color:#eee}button{font:inherit;padding:.6em 1.2em;border-radius:8px;border:0;background:#7c6cf2;color:#fff;cursor:pointer}\n",
            "app.js": "let n = 0;\ndocument.getElementById('go').addEventListener('click', () => { document.getElementById('out').textContent = ++n; });\n",
        },
        "electron-app": {
            "README.md": f"# {title}\n\n`npm install` then `npm start`. Package with `npm run dist` (electron-builder).\n",
            "package.json": json.dumps({"name": slug, "version": "0.1.0", "main": "main.js", "scripts": {"start": "electron .", "dist": "electron-builder"}, "devDependencies": {"electron": "^31.0.0", "electron-builder": "^24.13.3"}}, indent=2) + "\n",
            "main.js": "const { app, BrowserWindow } = require('electron');\nconst path = require('path');\nfunction create() {\n  const w = new BrowserWindow({ width: 900, height: 600, webPreferences: { contextIsolation: true } });\n  w.loadFile(path.join(__dirname, 'index.html'));\n}\napp.whenReady().then(create);\napp.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });\n",
            "index.html": f"<!doctype html><html><head><meta charset=\"utf-8\"><title>{title}</title></head><body style=\"font-family:system-ui;background:#111;color:#eee\"><h1>{title}</h1></body></html>\n",
        },
        "csharp-console": {
            "README.md": f"# {title}\n\n`dotnet run` · publish: `dotnet publish -c Release -r win-x64 --self-contained`\n",
            f"{mod}.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\">\n  <PropertyGroup>\n    <OutputType>Exe</OutputType>\n    <TargetFramework>net8.0</TargetFramework>\n    <Nullable>enable</Nullable>\n    <ImplicitUsings>enable</ImplicitUsings>\n  </PropertyGroup>\n</Project>\n",
            "Program.cs": f"Console.WriteLine(\"{title}\");\n",
        },
        "cpp-cmake": {
            "README.md": f"# {title}\n\n`cmake -S . -B build && cmake --build build`\n",
            "CMakeLists.txt": f"cmake_minimum_required(VERSION 3.16)\nproject({mod} CXX)\nset(CMAKE_CXX_STANDARD 20)\nadd_executable({mod} src/main.cpp)\n",
            "src/main.cpp": f"#include <iostream>\nint main() {{ std::cout << \"{title}\\n\"; return 0; }}\n",
        },
        "rust-cli": {
            "README.md": f"# {title}\n\n`cargo run` · `cargo build --release`\n",
            "Cargo.toml": f"[package]\nname = \"{mod}\"\nversion = \"0.1.0\"\nedition = \"2021\"\n\n[dependencies]\n",
            "src/main.rs": f"fn main() {{\n    println!(\"{title}\");\n}}\n",
        },
        "go-cli": {
            "README.md": f"# {title}\n\n`go run .` · `go build`\n",
            "go.mod": f"module {mod}\n\ngo 1.21\n",
            "main.go": f"package main\n\nimport \"fmt\"\n\nfunc main() {{\n\tfmt.Println(\"{title}\")\n}}\n",
        },
        "pygame-game": {
            "README.md": f"# {title}\n\n`pip install pygame` then `python main.py`\n",
            "requirements.txt": "pygame>=2.5\n",
            "main.py": f"import pygame\n\nW, H = 960, 540\n\n\ndef main():\n    pygame.init()\n    screen = pygame.display.set_mode((W, H))\n    pygame.display.set_caption('{title}')\n    clock = pygame.time.Clock()\n    x, y, speed = W // 2, H // 2, 300\n    running = True\n    while running:\n        dt = clock.tick(60) / 1000\n        for e in pygame.event.get():\n            if e.type == pygame.QUIT:\n                running = False\n        k = pygame.key.get_pressed()\n        x += (k[pygame.K_d] - k[pygame.K_a]) * speed * dt\n        y += (k[pygame.K_s] - k[pygame.K_w]) * speed * dt\n        screen.fill((18, 18, 26))\n        pygame.draw.circle(screen, (124, 108, 242), (int(x), int(y)), 18)\n        pygame.display.flip()\n    pygame.quit()\n\n\nif __name__ == '__main__':\n    main()\n",
        },
    }
    if name == "empty":
        return {"README.md": f"# {title}\n"}
    return T.get(name)


TEMPLATES = ["empty", "python-cli", "python-gui", "node-cli", "web-static", "electron-app", "csharp-console",
             "cpp-cmake", "rust-cli", "go-cli", "pygame-game"]
GITIGNORE = "node_modules/\n__pycache__/\n.venv/\ndist/\nbuild/\nbin/\nobj/\ntarget/\n.ms_snapshots/\n*.log\n"


# ── project detection / build recipes ───────────────────────────────────
def detect_project(root):
    r = Path(root)
    kinds = []
    if (r / "package.json").exists():
        try:
            pkg = json.loads((r / "package.json").read_text(encoding="utf-8"))
        except Exception:
            pkg = {}
        scripts = pkg.get("scripts") or {}
        deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
        pm = "pnpm" if (r / "pnpm-lock.yaml").exists() else "yarn" if (r / "yarn.lock").exists() else "npm"
        runs = (lambda n: f"{pm} run {n}")
        kinds.append({"kind": "node", "install": f"{pm} install", "build": runs("build") if "build" in scripts else None,
                      "test": f"{pm} test" if "test" in scripts else None, "run": f"{pm} start" if "start" in scripts else ("node ." if pkg.get("main") else None),
                      "package": runs("dist") if "dist" in scripts else runs("package") if "package" in scripts else None,
                      "lint": runs("lint") if "lint" in scripts else ("npx eslint ." if "eslint" in deps else None),
                      "format": runs("format") if "format" in scripts else ("npx prettier --write ." if "prettier" in deps else None),
                      "typecheck": runs("typecheck") if "typecheck" in scripts else ("npx tsc --noEmit" if (r / "tsconfig.json").exists() else None)})
    if list(r.glob("*.csproj")) or list(r.glob("*.sln")):
        kinds.append({"kind": "dotnet", "install": "dotnet restore", "build": "dotnet build -c Release", "test": "dotnet test",
                      "run": "dotnet run", "package": "dotnet publish -c Release",
                      "lint": "dotnet format --verify-no-changes", "format": "dotnet format", "typecheck": "dotnet build -c Release"})
    if (r / "Cargo.toml").exists():
        kinds.append({"kind": "rust", "install": "cargo fetch", "build": "cargo build --release", "test": "cargo test", "run": "cargo run", "package": "cargo build --release",
                      "lint": "cargo clippy -- -D warnings", "format": "cargo fmt", "typecheck": "cargo check"})
    if (r / "go.mod").exists():
        kinds.append({"kind": "go", "install": "go mod download", "build": "go build ./...", "test": "go test ./...", "run": "go run .", "package": "go build -o dist/ .",
                      "lint": "go vet ./...", "format": "gofmt -w .", "typecheck": "go vet ./..."})
    if (r / "CMakeLists.txt").exists():
        kinds.append({"kind": "cmake", "install": None, "build": "cmake -S . -B build && cmake --build build --config Release", "test": "ctest --test-dir build", "run": None, "package": "cmake --build build --config Release", "lint": None, "format": "clang-format -i $(git ls-files '*.cpp' '*.h')" if os.name != "nt" else None, "typecheck": "cmake --build build"})
    elif (r / "Makefile").exists():
        kinds.append({"kind": "make", "install": None, "build": "make", "test": "make test", "run": None, "package": "make", "lint": None, "format": None, "typecheck": None})
    py = (r / "pyproject.toml").exists() or (r / "requirements.txt").exists() or list(r.glob("*.py"))
    if py:
        entry = next((n for n in ("main.py", "app.py") if (r / n).exists()), None)
        pyexe = '"%s"' % sys.executable if sys.executable else "python"
        kinds.append({"kind": "python", "install": f"{pyexe} -m pip install -r requirements.txt" if (r / "requirements.txt").exists() else (f"{pyexe} -m pip install -e ." if (r / "pyproject.toml").exists() else None),
                      "build": f"{pyexe} -m compileall -q .", "test": f"{pyexe} -m unittest discover -s tests" if (r / "tests").is_dir() else f"{pyexe} -m unittest",
                      "run": f"{pyexe} {entry}" if entry else None, "package": f"pyinstaller --onefile {entry}" if entry else None,
                      "lint": (f"{pyexe} -m ruff check ." if shutil.which("ruff") else f"{pyexe} -m pyflakes ." if shutil.which("pyflakes") else f"{pyexe} -m compileall -q ."),
                      "format": (f"{pyexe} -m ruff format ." if shutil.which("ruff") else f"{pyexe} -m black ." if shutil.which("black") else None),
                      "typecheck": (f"{pyexe} -m mypy ." if shutil.which("mypy") else f"{pyexe} -m compileall -q .")})
    if not kinds and (r / "index.html").exists():
        kinds.append({"kind": "web-static", "install": None, "build": None, "test": None, "run": f'"{sys.executable}" -m http.server 8000' if sys.executable else None, "package": None, "lint": None, "format": None, "typecheck": None})
    if (r / "project.godot").exists():
        kinds.append({"kind": "godot", "install": None, "build": "godot --headless --import", "test": None, "run": "godot --path .", "package": None, "lint": None, "format": None, "typecheck": "godot --headless --check-only --quit"})
    return kinds


DANGER = [r"\brm\s+-rf\s+(/|~|\*|\$HOME)(\s|$)", r"\bformat\s+[a-z]:", r"\bdel\s+/[sq].*[a-z]:\\\s*$", r"\bshutdown\b", r"\bmkfs\b",
          r"\bdd\s+if=.*of=/dev/", r":\(\)\s*\{\s*:\|:&\s*\};:", r"\breg\s+delete\s+HK", r"\bRemove-Item\b.*-Recurse.*[A-Za-z]:\\\s*$",
          r"\bdiskpart\b", r"\bcipher\s+/w", r"\bbcdedit\b"]


def _danger(cmd):
    for pat in DANGER:
        if re.search(pat, cmd, re.I):
            return pat
    return None


def _env(extra=None):
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("CI", "1")  # no interactive prompts / watch modes
    env.setdefault("GIT_PAGER", "cat")
    if isinstance(extra, dict):
        env.update({str(k): str(v) for k, v in extra.items() if str(k)})
    return env


def _run(cmd, cwd, timeout, env=None):
    cap = edition.policy().get("workspace",{}).get("maxCommandSeconds")
    if cap: timeout = min(timeout, int(cap))
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=str(cwd), shell=True, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, env=env or _env(), **_nowin())
        return {"ok": r.returncode == 0, "exit_code": r.returncode, "seconds": round(time.time() - t0, 2),
                "stdout": _clip(r.stdout), "stderr": _clip(r.stderr)}
    except subprocess.TimeoutExpired as e:
        return {"ok": False, "exit_code": None, "timed_out": True, "seconds": timeout,
                "stdout": _clip(e.stdout if isinstance(e.stdout, str) else ""), "stderr": _clip(e.stderr if isinstance(e.stderr, str) else ""),
                "hint": "Long-running process (server/GUI)? Use ms_ws_run with background:true, then ms_ws_process."}


def _pick_folder_dialog(title):
    """Opens a native folder picker in a CHILD process (Tk must own its thread)."""
    code = ("import tkinter as tk\nfrom tkinter import filedialog\nr=tk.Tk();r.withdraw();r.attributes('-topmost',True)\n"
            f"p=filedialog.askdirectory(title={title!r},mustexist=False)\nprint(p or '')\n")
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600)
        p = (r.stdout or "").strip()
        if p:
            return p
    except Exception:
        pass
    if sys.platform == "darwin":
        try:
            r = subprocess.run(["osascript", "-e", f'POSIX path of (choose folder with prompt "{title}")'], capture_output=True, text=True, timeout=600)
            return (r.stdout or "").strip() or None
        except Exception:
            return None
    if os.name == "nt":
        ps = ("Add-Type -AssemblyName System.Windows.Forms;$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
              f"$d.Description='{title}';if($d.ShowDialog() -eq 'OK'){{$d.SelectedPath}}")
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", ps], capture_output=True, text=True, timeout=600)
            return (r.stdout or "").strip() or None
        except Exception:
            return None
    return None


# ── tool schemas ─────────────────────────────────────────────────────────
S = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}
STR = {"type": "string"}
def _int(v, default, lo=None, hi=None):
    """Tolerant integer argument: accepts 5, 5.0, "5", " 5 ", "5.7"; falls back to `default`
    on junk and CLAMPS to [lo, hi] instead of rejecting (models routinely send strings/floats,
    and a schema that rejects them surfaces as a 'JSON error' in the chat)."""
    try:
        if isinstance(v, bool) or v is None or v == "":
            n = int(default)
        else:
            n = int(float(str(v).strip()))
    except (TypeError, ValueError):
        n = int(default)
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def D(t, desc, **kw):
    d = {"type": t, "description": desc}
    d.update(kw)
    return d


PATH = D("string", "Path relative to the workspace root (forward slashes). '.' is the root.")
BUILD_STEPS = ["detect", "install", "build", "test", "run", "package", "lint", "format", "typecheck"]
TOOLS = [
    {"name": "ms_ws_status", "description": "Workspace: show the root folder, session mode (build|code), whether commands may run, detected toolchains, git state and the detected project type with install/build/test/run/package/lint/format/typecheck recipes. Call first.", "inputSchema": S({})},
    {"name": "ms_ws_pick_folder", "description": "Workspace: open a native folder picker ON THE USER'S PC so they choose the workspace folder. Blocks until they choose or cancel.", "inputSchema": S({"title": D("string", "Dialog title shown to the user.")})},
    {"name": "ms_ws_create_project", "description": "Workspace: create a NEW project folder (in 'Multi-Script Projects', or inside the current root with inside_root=true), scaffold a template and make it the root. Templates: " + ", ".join(TEMPLATES) + ".", "inputSchema": S({"name": D("string", "Project/app name (also the folder name)."), "template": D("string", "Starter template.", enum=TEMPLATES), "inside_root": D("boolean", "Create inside the current workspace root instead of the projects folder.")}, ["name"])},
    {"name": "ms_ws_tree", "description": "Workspace: list files under a path (skips node_modules, .git, build outputs) with sizes and line counts.", "inputSchema": S({"path": PATH, "depth": D("integer", "Folder depth, 1-8 (default 4)."), "max_entries": D("integer", "Max files, 1-2000 (default 400)."), "pattern": D("string", "Optional filename glob filter, e.g. '*.ts'.")})},
    {"name": "ms_ws_glob", "description": "Workspace: find files by glob pattern across the project, e.g. 'src/**/*.ts' or '**/test_*.py'. Newest first.", "inputSchema": S({"pattern": D("string", "Glob relative to the root. '**' matches any folders."), "max_results": D("integer", "1-1000 (default 200).")}, ["pattern"])},
    {"name": "ms_ws_read", "description": "Workspace: read a text file, optionally a 1-based inclusive line range. Output is line-numbered ('  12| code') for exact edits - never copy the number prefix into edits.", "inputSchema": S({"path": PATH, "start_line": D("integer", "First line, 1-based (default 1)."), "end_line": D("integer", "Last line, inclusive (default end of file).")}, ["path"])},
    {"name": "ms_ws_read_many", "description": "Workspace: read several files in one call (each clipped to max_lines). Use to load related files together.", "inputSchema": S({"paths": {"type": "array", "items": PATH, "description": "Files to read (max 20)."}, "max_lines": D("integer", "Lines per file, 1-2000 (default 400).")}, ["paths"])},
    {"name": "ms_ws_outline", "description": "Workspace: list the symbols (classes, functions, types, headings) of a file with line numbers - Python, JS/TS, Go, Rust, C#, Java, Kotlin, C/C++, GDScript, Lua/Luau, Ruby, PHP, Swift, Markdown.", "inputSchema": S({"path": PATH}, ["path"])},
    {"name": "ms_ws_write", "description": "Workspace: write a whole text file (creates folders). mode: overwrite (default), create (fail if it exists) or append. Backed up for ms_ws_undo; returns a diff summary.", "inputSchema": S({"path": PATH, "content": D("string", "The complete file content."), "mode": D("string", "Write mode.", enum=["overwrite", "create", "append"])}, ["path", "content"])},
    {"name": "ms_ws_edit", "description": "Workspace: targeted edits in ONE file, applied atomically in order. Each edit is either {old_string,new_string} (old_string must match exactly once - CRLF and trailing whitespace are tolerated - or set replace_all) or {start_line,end_line,new_string} to replace a line range. dry_run returns the diff only.", "inputSchema": S({"path": PATH, "edits": {"type": "array", "description": "Edits applied in order.", "items": {"type": "object", "properties": {"old_string": D("string", "Exact text to replace (copied from ms_ws_read without the line-number prefix)."), "new_string": D("string", "Replacement text."), "replace_all": D("boolean", "Replace every occurrence of old_string."), "start_line": D("integer", "Line-range form: first line to replace (1-based)."), "end_line": D("integer", "Line-range form: last line to replace (inclusive).")}, "required": ["new_string"]}}, "dry_run": D("boolean", "Preview the diff without writing.")}, ["path", "edits"])},
    {"name": "ms_ws_patch", "description": "Workspace: apply a unified diff (git diff / diff -u format, one or many files, new files via '--- /dev/null'). Hunks are matched by context, so line numbers may be approximate. All-or-nothing; dry_run checks only.", "inputSchema": S({"patch": D("string", "The unified diff text."), "dry_run": D("boolean", "Validate without writing.")}, ["patch"])},
    {"name": "ms_ws_search", "description": "Workspace: search file contents (plain text or regex) with optional glob filter, sub-folder and context lines.", "inputSchema": S({"query": D("string", "Text or regex to find."), "regex": D("boolean", "Treat query as a regular expression."), "case_sensitive": D("boolean", "Match case (default false)."), "glob": D("string", "Filename filter, e.g. '*.py'."), "path": PATH, "context": D("integer", "Lines of context around each hit, 0-5 (default 0)."), "max_results": D("integer", "1-500 (default 100).")}, ["query"])},
    {"name": "ms_ws_replace", "description": "Workspace: project-wide find/replace across files matching a glob. Always run with dry_run=true first to see every change; the real run is backed up for ms_ws_undo.", "inputSchema": S({"query": D("string", "Text or regex to replace."), "replacement": D("string", "Replacement (regex mode supports \\1 groups)."), "regex": D("boolean", "Treat query as a regular expression."), "case_sensitive": D("boolean", "Match case (default true)."), "glob": D("string", "Filename filter, e.g. '*.ts' (default all text files)."), "dry_run": D("boolean", "Preview only (default true).")}, ["query", "replacement"])},
    {"name": "ms_ws_move", "description": "Workspace: move or rename a file/folder inside the workspace.", "inputSchema": S({"from_path": PATH, "to_path": PATH}, ["from_path", "to_path"])},
    {"name": "ms_ws_delete", "description": "Workspace: delete a file/folder inside the workspace. Requires confirm=true. Never deletes the root. Files are backed up for ms_ws_undo.", "inputSchema": S({"path": PATH, "confirm": D("boolean", "Must be true.")}, ["path", "confirm"])},
    {"name": "ms_ws_undo", "description": "Workspace: undo recent file changes made by ms_ws_write/edit/patch/replace/delete (newest first). list shows the journal.", "inputSchema": S({"action": D("string", "undo (default) or list.", enum=["undo", "list"]), "steps": D("integer", "How many changes to undo, 1-40 (default 1)."), "path": D("string", "Only undo changes to this file.")})},
    {"name": "ms_ws_diff", "description": "Workspace: show what changed - git diff when the folder is a git repo, otherwise the diff of each file against its last ms_ws_undo backup.", "inputSchema": S({"path": D("string", "Limit to one file/folder."), "staged": D("boolean", "git: show staged changes.")})},
    {"name": "ms_ws_git", "description": "Workspace: git in the workspace. Read-only actions (status, diff, log, show, branch_list, blame) always work; init, add, commit, branch, checkout, stash, restore need 'Run commands'.", "inputSchema": S({"action": D("string", "Git action.", enum=["status", "diff", "log", "show", "branch_list", "blame", "init", "add", "commit", "branch", "checkout", "stash", "restore"]), "paths": {"type": "array", "items": {"type": "string"}, "description": "Files for add/restore/diff/blame."}, "message": D("string", "Commit message."), "ref": D("string", "Branch/commit for show, branch, checkout."), "max_count": D("integer", "log: number of commits (default 15).")}, ["action"])},
    {"name": "ms_ws_run", "description": "Workspace: run a shell command in the workspace (requires 'Run commands'). Returns exit code + output head/tail. background=true starts a long-running process (dev server, GUI) and returns an id for ms_ws_process.", "inputSchema": S({"command": D("string", "The shell command."), "cwd": PATH, "timeout_s": D("integer", "Seconds, 1-1800 (default 180)."), "background": D("boolean", "Start and return immediately."), "env": {"type": "object", "additionalProperties": {"type": "string"}, "description": "Extra environment variables."}}, ["command"])},
    {"name": "ms_ws_process", "description": "Workspace: list background processes, read one's recent output, or stop it (whole process tree).", "inputSchema": S({"action": D("string", "What to do.", enum=["list", "output", "stop"]), "id": D("string", "Process id from ms_ws_run.")}, ["action"])},
    {"name": "ms_ws_build", "description": "Workspace: auto-detect the project (node/pnpm/yarn, python, dotnet, rust, go, cmake, make, godot, static web) and run its canonical step. detect shows the recipes without running anything.", "inputSchema": S({"step": D("string", "Step to run.", enum=BUILD_STEPS), "kind": D("string", "Pick one detected project kind when several exist (e.g. node)."), "timeout_s": D("integer", "Seconds, 5-1800.")}, ["step"])},
    {"name": "ms_ws_check", "description": "Workspace: one-shot verification - runs every available typecheck, lint and test recipe and reports pass/fail per step with the first errors. Use before saying work is done.", "inputSchema": S({"steps": {"type": "array", "items": {"type": "string", "enum": ["typecheck", "lint", "test", "build"]}, "description": "Subset to run (default typecheck, lint, test)."}, "timeout_s": D("integer", "Seconds per step (default 300).")})},
    {"name": "ms_ws_http", "description": "Workspace: send an HTTP request to a LOCAL server (localhost / 127.0.0.1 only) to test a dev server or API you started.", "inputSchema": S({"url": D("string", "http://localhost:PORT/path or http://127.0.0.1:PORT/path."), "method": D("string", "HTTP method.", enum=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]), "body": D("string", "Request body (send JSON as a string)."), "headers": {"type": "object", "additionalProperties": {"type": "string"}, "description": "Request headers."}, "timeout_s": D("integer", "Seconds (default 15).")}, ["url"])},
    {"name": "ms_ws_plan", "description": "Workspace: keep a visible task plan for multi-step work. set replaces the plan, update changes item statuses, show prints it. Statuses: todo, doing, done, blocked.", "inputSchema": S({"action": D("string", "Plan action.", enum=["set", "update", "show", "clear"]), "items": {"type": "array", "description": "set: the steps; update: {id,status} pairs.", "items": {"type": "object", "properties": {"id": D("integer", "Step number (1-based)."), "text": D("string", "Step description (set)."), "status": D("string", "Step status.", enum=["todo", "doing", "done", "blocked"]), "note": D("string", "Optional note/evidence.")}}}}, ["action"])},
    {"name": "ms_ws_snapshot", "description": "Workspace: create, list or restore a zip snapshot of the project (excludes build outputs) - take one before large refactors.", "inputSchema": S({"action": D("string", "Snapshot action.", enum=["create", "list", "restore"]), "name": D("string", "restore: snapshot file name from list."), "label": D("string", "create: short label.")}, ["action"])},
    {"name": "ms_ws_package_zip", "description": "Workspace: zip the project source (no node_modules/build junk) into dist/<name>.zip for sharing.", "inputSchema": S({"name": D("string", "Zip name without extension (default: folder name).")})},
]
INTERNAL = {"name": "ms_ws_configure", "description": "INTERNAL (extension only): enable Software Builder / Code mode and set root, mode and permissions.", "inputSchema": S({"enabled": D("boolean", "Enable workspace tools."), "root": D("string", "Absolute workspace folder."), "allow_run": D("boolean", "Allow commands."), "projects_dir": D("string", "Folder for new projects."), "mode": D("string", "Session mode.", enum=["build", "code"])})}
TOOLS.append(INTERNAL)
TOOL_NAMES = {t["name"] for t in TOOLS}


# ── implementations ──────────────────────────────────────────────────────
def _walk(base, depth, limit):
    rows, n = [], 0
    base = Path(base)
    for dirpath, dirs, files in os.walk(base):
        d = Path(dirpath)
        lvl = len(d.relative_to(base).parts)
        dirs[:] = sorted(x for x in dirs if x not in IGNORE_DIRS and not x.startswith(".ms_"))
        if lvl >= depth:
            dirs[:] = []
        for f in sorted(files):
            p = d / f
            try:
                size = p.stat().st_size
            except OSError:
                continue
            row = {"path": _rel(p), "bytes": size}
            if size < 400_000:
                try:
                    row["lines"] = p.read_bytes().count(b"\n") + 1
                except Exception:
                    pass
            rows.append(row)
            n += 1
            if n >= limit:
                return rows, True
    return rows, False


def _snap_dir():
    d = _root() / ".ms_snapshots"
    d.mkdir(exist_ok=True)
    return d


def _zip_project(dest):
    root = _root()
    count = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x not in IGNORE_DIRS]
            for f in files:
                p = Path(dirpath) / f
                if p.resolve() == Path(dest).resolve():
                    continue
                z.write(p, p.relative_to(root))
                count += 1
    return count


def call_tool(name, args):
    args = args or {}
    product_limit = edition.check(name,args)
    if product_limit: return _err(product_limit)
    s = _load()
    if name == "ms_ws_configure":
        if "enabled" in args:
            s["enabled"] = bool(args["enabled"])
        if "allow_run" in args:
            s["allow_run"] = bool(args["allow_run"])
        if args.get("projects_dir"):
            s["projects_dir"] = str(Path(os.path.expanduser(args["projects_dir"])))
        if args.get("mode") in ("build", "code"):
            s["mode"] = args["mode"]
        if args.get("root"):
            p = Path(os.path.expanduser(str(args["root"])))
            p.mkdir(parents=True, exist_ok=True)
            s["root"] = str(p.resolve())
        _save(s)
        return _out({"ok": True, "enabled": s.get("enabled", False), "root": s.get("root"), "allow_run": s.get("allow_run", False), "mode": s.get("mode", "build")})

    if not s.get("enabled"):
        return _err(_require_enabled())

    if name == "ms_ws_pick_folder":
        p = _pick_folder_dialog(str(args.get("title") or "Choose a Multi-Script workspace folder"))
        if not p:
            return _err("The user cancelled the folder picker (or no desktop dialog is available). Ask them which folder to use, or call ms_ws_create_project.")
        s["root"] = str(Path(p).resolve())
        _save(s)
        return _out({"ok": True, "root": s["root"], "next": "Call ms_ws_status, then ms_ws_tree."})

    if name == "ms_ws_create_project":
        title = str(args.get("name") or "").strip()[:80] or "New App"
        folder = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", title).strip(" .-") or "New-App"
        parent = _root() if args.get("inside_root") and _root() else Path(s.get("projects_dir") or DEFAULT_PROJECTS_DIR)
        parent.mkdir(parents=True, exist_ok=True)
        dest = parent / folder
        i = 2
        while dest.exists() and any(dest.iterdir()):
            dest = parent / f"{folder}-{i}"
            i += 1
        dest.mkdir(parents=True, exist_ok=True)
        tpl = str(args.get("template") or "empty")
        files = _tpl(tpl, title)
        if files is None:
            return _err(f"unknown template '{tpl}'", templates=TEMPLATES)
        files = dict(files)
        files.setdefault(".gitignore", GITIGNORE)
        for rel, content in files.items():
            fp = dest / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
        s["root"] = str(dest.resolve())
        _save(s)
        return _out({"ok": True, "root": s["root"], "template": tpl, "files": sorted(files), "recipes": detect_project(dest)})

    problem = _require_enabled()
    if problem:
        return _err(problem)
    root = _root()
    try:
        if name == "ms_ws_status":
            git = None
            if (root / ".git").exists() and shutil.which("git"):
                g = _run("git status --short --branch", root, 20)
                git = {"repo": True, "status": (g.get("stdout") or "").strip()[:2000]}
            files, cut = _walk(root, 3, 60)
            return _out({"ok": True, "root": str(root), "mode": s.get("mode", "build"), "allow_run": bool(s.get("allow_run")), "toolchains": detect_toolchains(),
                         "project": detect_project(root), "git": git or {"repo": False}, "top_files": [f["path"] for f in files], "more_files": cut,
                         "templates": TEMPLATES, "os": sys.platform,
                         "next": "ms_ws_tree / ms_ws_glob to explore, ms_ws_read before ms_ws_edit, ms_ws_check before reporting done."})
        if name == "ms_ws_tree":
            base = _safe(args.get("path") or ".", must_exist=True)
            rows, cut = _walk(base, _int(args.get("depth"), 4, 1, 8), _int(args.get("max_entries"), 400, 1, 2000))
            if args.get("pattern"):
                pat = str(args["pattern"])
                rows = [r_ for r_ in rows if fnmatch.fnmatch(r_["path"].rsplit("/", 1)[-1], pat) or fnmatch.fnmatch(r_["path"], pat)]
            return _out({"ok": True, "root": str(root), "base": _rel(base), "files": rows, "truncated": cut})
        if name == "ms_ws_read":
            p = _safe(args["path"], must_exist=True)
            if p.is_dir():
                return _err("that path is a folder - use ms_ws_tree")
            raw = p.read_bytes()
            if b"\x00" in raw[:4096]:
                return _err("binary file - not shown", bytes=len(raw))
            lines = raw.decode("utf-8", errors="replace").splitlines()
            a = _int(args.get("start_line"), 1, 1)
            b = min(len(lines), _int(args.get("end_line"), len(lines), 1))
            body = "\n".join(f"{i:>5}| {lines[i - 1]}" for i in range(a, b + 1))
            if len(body) > MAX_READ:
                body = body[:MAX_READ] + "\n…[truncated - read a smaller line range]"
            return _out(f"{_rel(p)} (lines {a}-{b} of {len(lines)})\n{body}")
        if name == "ms_ws_write":
            p = _safe(args["path"])
            content = str(args.get("content") or "")
            if len(content) > MAX_WRITE:
                return _err("content too large (2 MB max per write)")
            mode = args.get("mode") or "overwrite"
            if mode == "create" and p.exists():
                return _err(f"{_rel(p)} already exists (mode=create)")
            if p.is_dir():
                return _err(f"{_rel(p)} is a folder")
            p.parent.mkdir(parents=True, exist_ok=True)
            existed = p.exists()
            before = ""
            if existed:
                try:
                    before = _read_text(p)
                except ValueError:
                    before = ""
            _backup(p, "write")
            with open(p, "a" if mode == "append" else "w", encoding="utf-8", newline="") as fh:
                fh.write(content)
            after = before + content if mode == "append" else content
            d = _diff(before, after, _rel(p), 0, 1500) if existed else ""
            added = sum(1 for ln in d.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
            removed = sum(1 for ln in d.splitlines() if ln.startswith("-") and not ln.startswith("---"))
            return _out({"ok": True, "path": _rel(p), "mode": mode, "created": not existed, "bytes": p.stat().st_size, "lines": after.count("\n") + 1,
                         "changed_lines": {"added": added, "removed": removed} if existed else None, "undo": "ms_ws_undo"})
        if name == "ms_ws_edit":
            p = _safe(args["path"], must_exist=True)
            if p.is_dir():
                return _err("that path is a folder")
            text = _read_text(p)
            orig, report = text, []
            edits = args.get("edits")
            if isinstance(edits, dict):
                edits = [edits]
            if isinstance(edits, str):
                try:
                    edits = json.loads(edits)
                except Exception:
                    return _err("edits must be an array of {old_string,new_string} objects")
            if not edits and ("old_string" in args or "start_line" in args):
                edits = [{k: args[k] for k in ("old_string", "new_string", "replace_all", "start_line", "end_line") if k in args}]
            if not edits:
                return _err("no edits given", example={"path": "src/app.py", "edits": [{"old_string": "x = 1", "new_string": "x = 2"}]})
            for i, e in enumerate(edits):
                if not isinstance(e, dict):
                    return _err(f"edit {i + 1} is not an object - nothing was changed")
                new = str(e.get("new_string", e.get("new", "")))
                if e.get("start_line") not in (None, "") and not e.get("old_string"):
                    lines = text.splitlines(True)
                    a_ = _int(e.get("start_line"), 1, 1, max(1, len(lines) + 1))
                    b_ = _int(e.get("end_line"), a_, a_ - 1, len(lines))
                    nl = _adapt_eol(text, new)
                    if nl and not nl.endswith(("\n", "\r")) and b_ < len(lines):
                        nl += "\r\n" if "\r\n" in text else "\n"
                    text = "".join(lines[:a_ - 1]) + nl + "".join(lines[b_:])
                    report.append({"edit": i + 1, "lines": f"{a_}-{b_}", "how": "line-range"})
                    continue
                old = str(e.get("old_string", e.get("old", "")))
                if not old:
                    return _err(f"edit {i + 1}: old_string is empty (or give start_line/end_line) - nothing was changed")
                if e.get("replace_all"):
                    n = text.count(old)
                    if n == 0 and "\r\n" in text:
                        old, new = old.replace("\n", "\r\n"), _adapt_eol(text, new)
                        n = text.count(old)
                    if n == 0:
                        return _err(f"edit {i + 1}: old_string not found - nothing was changed")
                    text = text.replace(old, new)
                    report.append({"edit": i + 1, "replaced": n, "how": "replace_all"})
                    continue
                n = text.count(old)
                if n > 1:
                    return _err(f"edit {i + 1}: old_string matches {n} times - add surrounding lines or set replace_all=true; nothing was changed")
                hit = _find_flex(text, old)
                if not hit:
                    first = old.strip().splitlines()[0].strip() if old.strip() else old
                    near = [f"{k + 1}: {ln}" for k, ln in enumerate(text.splitlines()) if first[:40] and first[:40].strip() and first[:40] in ln][:3]
                    if not near:
                        cands = difflib.get_close_matches(first, [ln.strip() for ln in text.splitlines()], 3, 0.6)
                        near = [f"{k + 1}: {ln}" for k, ln in enumerate(text.splitlines()) if ln.strip() in cands][:3]
                    return _err(f"edit {i + 1}: old_string not found - nothing was changed", closest_lines=near,
                                hint="ms_ws_read the lines again and copy them exactly without the 'NN| ' prefix, or use start_line/end_line.")
                st, en, how = hit
                text = text[:st] + (_adapt_eol(text, new) if how != "exact" else new) + text[en:]
                report.append({"edit": i + 1, "replaced": 1, "how": how})
            d = _diff(orig, text, _rel(p))
            if args.get("dry_run"):
                return _out({"ok": True, "dry_run": True, "path": _rel(p), "edits": report, "diff": d})
            if text == orig:
                return _out({"ok": True, "path": _rel(p), "edits": report, "note": "the edits produced no change"})
            _backup(p, "edit")
            _write_text(p, text)
            return _out({"ok": True, "path": _rel(p), "edits": report, "lines": text.count("\n") + 1, "diff": d})
        if name == "ms_ws_patch":
            files = _parse_patch(str(args.get("patch") or ""))
            if not files:
                return _err("no file headers found - give a unified diff with '--- a/path' and '+++ b/path' lines and @@ hunks")
            results, staged = [], []
            for rel, f in files.items():
                p = _safe(rel)
                if f.get("delete"):
                    staged.append((p, None)); results.append({"path": rel, "action": "delete"}); continue
                base = "" if f.get("new") or not p.exists() else _read_text(p)
                try:
                    if f.get("new") and not base:
                        after = "".join(ln + "\n" for h in f["hunks"] for ln in h[1])
                    else:
                        after = _apply_hunks(base, f["hunks"])
                except ValueError as exc:
                    return _err(f"{rel}: {exc} - nothing was changed", hint="ms_ws_read the file and rebuild the hunk from its current text, or use ms_ws_edit.")
                staged.append((p, after)); results.append({"path": rel, "action": "create" if not base else "modify", "hunks": len(f["hunks"])})
            if args.get("dry_run"):
                return _out({"ok": True, "dry_run": True, "files": results})
            for p, after in staged:
                _backup(p, "patch")
                if after is None:
                    if p.exists():
                        p.unlink()
                else:
                    _write_text(p, after)
            return _out({"ok": True, "files": results, "undo": "ms_ws_undo"})
        if name == "ms_ws_glob":
            pat = str(args.get("pattern") or "*").replace("\\", "/").lstrip("./")
            limit = _int(args.get("max_results"), 200, 1, 1000)
            hits = []
            for dirpath, dirs, fs in os.walk(root):
                dirs[:] = [x for x in dirs if x not in IGNORE_DIRS and not x.startswith(".ms_")]
                for f in fs:
                    rp = _rel(Path(dirpath) / f)
                    if fnmatch.fnmatch(rp, pat) or fnmatch.fnmatch(rp, pat.replace("**/", "")) or ("/" not in pat and fnmatch.fnmatch(f, pat)):
                        try:
                            hits.append((Path(dirpath, f).stat().st_mtime, rp))
                        except OSError:
                            pass
            hits.sort(reverse=True)
            return _out({"ok": True, "pattern": pat, "count": len(hits), "files": [h[1] for h in hits[:limit]], "truncated": len(hits) > limit})
        if name == "ms_ws_read_many":
            paths = args.get("paths") or []
            if isinstance(paths, str):
                paths = [x.strip() for x in re.split(r"[,\n]", paths) if x.strip()]
            mx = _int(args.get("max_lines"), 400, 1, 2000)
            parts = []
            for rel in list(paths)[:20]:
                try:
                    p = _safe(rel, must_exist=True)
                    lines = _read_text(p).splitlines()
                    body = "\n".join(f"{i:>5}| {lines[i - 1]}" for i in range(1, min(len(lines), mx) + 1))
                    more = f"\n…[{len(lines) - mx} more lines - ms_ws_read with start_line={mx + 1}]" if len(lines) > mx else ""
                    parts.append(f"=== {_rel(p)} ({len(lines)} lines)\n{body}{more}")
                except Exception as exc:
                    parts.append(f"=== {rel}\nERROR: {exc}")
            out = "\n\n".join(parts)
            return _out(out if len(out) <= MAX_READ else out[:MAX_READ] + "\n…[truncated - read fewer files]")
        if name == "ms_ws_outline":
            p = _safe(args["path"], must_exist=True)
            rx = next((re.compile(r, re.M) for pat, r in OUTLINE if re.search(pat, p.name, re.I)), None)
            if rx is None:
                return _err(f"no outline rules for {p.suffix or p.name}", hint="use ms_ws_search for 'def |class |function '")
            rows = []
            for k, ln in enumerate(_read_text(p).splitlines(), 1):
                m = rx.match(ln)
                if m and m.group(2) not in ("if", "for", "while", "switch", "return", "catch", "else"):
                    rows.append(f"{k:>5}  {m.group(1).strip()} {m.group(2).strip()}" + ("  (nested)" if ln[:1] in " \t" else ""))
            return _out(f"{_rel(p)} - {len(rows)} symbols\n" + "\n".join(rows[:600]))
        if name == "ms_ws_search":
            q = str(args["query"])
            flags = 0 if args.get("case_sensitive") else re.I
            try:
                rx = re.compile(q if args.get("regex") else re.escape(q), flags)
            except re.error as exc:
                return _err(f"bad regex: {exc}", hint="set regex=false to search literally")
            glob = args.get("glob")
            base = _safe(args.get("path") or ".", must_exist=True)
            limit = _int(args.get("max_results"), 100, 1, 500)
            ctx_n = _int(args.get("context"), 0, 0, 5)
            hits, files_hit = [], set()
            for dirpath, dirs, files in os.walk(base):
                dirs[:] = [x for x in dirs if x not in IGNORE_DIRS and not x.startswith(".ms_")]
                for f in sorted(files):
                    if glob and not (fnmatch.fnmatch(f, glob) or fnmatch.fnmatch(_rel(Path(dirpath) / f), glob)):
                        continue
                    p = Path(dirpath) / f
                    try:
                        if p.stat().st_size > 1_500_000:
                            continue
                        raw = p.read_bytes()
                        if b"\x00" in raw[:2048]:
                            continue
                        lines = raw.decode("utf-8", errors="ignore").splitlines()
                    except Exception:
                        continue
                    for k, ln in enumerate(lines, 1):
                        if rx.search(ln):
                            files_hit.add(_rel(p))
                            if ctx_n:
                                lo, hi = max(1, k - ctx_n), min(len(lines), k + ctx_n)
                                hits.append("\n".join(f"{_rel(p)}:{j}{':' if j == k else '-'} {lines[j - 1].rstrip()[:240]}" for j in range(lo, hi + 1)) + "\n--")
                            else:
                                hits.append(f"{_rel(p)}:{k}: {ln.strip()[:240]}")
                            if len(hits) >= limit:
                                return _out("\n".join(hits) + f"\n…[limit {limit} reached in {len(files_hit)} files - narrow with glob/path]")
            return _out(("\n".join(hits) + f"\n[{len(hits)} matches in {len(files_hit)} files]") if hits else f"no matches for {q!r}")
        if name == "ms_ws_replace":
            q = str(args.get("query") or "")
            if not q:
                return _err("query is empty")
            repl = str(args.get("replacement") if args.get("replacement") is not None else "")
            flags = 0 if args.get("case_sensitive", True) else re.I
            try:
                rx = re.compile(q if args.get("regex") else re.escape(q), flags)
            except re.error as exc:
                return _err(f"bad regex: {exc}")
            dry = args.get("dry_run") is not False
            glob = args.get("glob")
            changes, total = [], 0
            for dirpath, dirs, files in os.walk(root):
                dirs[:] = [x for x in dirs if x not in IGNORE_DIRS and not x.startswith(".ms_")]
                for f in files:
                    if glob and not (fnmatch.fnmatch(f, glob) or fnmatch.fnmatch(_rel(Path(dirpath) / f), glob)):
                        continue
                    p = Path(dirpath) / f
                    try:
                        if p.stat().st_size > 1_500_000:
                            continue
                        text = _read_text(p)
                    except Exception:
                        continue
                    new, n = rx.subn(repl if args.get("regex") else repl.replace("\\", "\\\\"), text)
                    if n:
                        total += n
                        changes.append({"path": _rel(p), "replacements": n, "diff": _diff(text, new, _rel(p), 0, 800)})
                        if not dry:
                            _backup(p, "replace")
                            _write_text(p, new)
                    if len(changes) >= 200:
                        break
            return _out({"ok": True, "dry_run": dry, "files": len(changes), "replacements": total, "changes": changes[:60],
                         "next": "Run again with dry_run=false to apply." if dry and changes else None})
        if name == "ms_ws_undo":
            j = _journal()
            if args.get("action") == "list":
                return _out({"ok": True, "changes": [{"n": len(j) - i, "path": e["path"], "op": e["op"], "age_s": round(time.time() - e["t"])} for i, e in enumerate(j)][::-1][:40]})
            want = str(args.get("path") or "").strip().replace("\\", "/")
            steps = _int(args.get("steps"), 1, 1, UNDO_KEEP)
            done = []
            for e in reversed(list(j)):
                if len(done) >= steps:
                    break
                if want and e["path"] != want:
                    continue
                p = _safe(e["path"])
                if e.get("existed") and e.get("blob"):
                    p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(_undo_dir() / e["blob"], p)
                    done.append({"path": e["path"], "restored": e["op"]})
                elif not e.get("existed"):
                    if p.exists() and p.is_file():
                        p.unlink()
                    done.append({"path": e["path"], "removed_new_file": True})
                j.remove(e)
            _journal_path().write_text(json.dumps(j, indent=1), encoding="utf-8")
            return _out({"ok": bool(done), "undone": done, "remaining": len(j)} if done else {"ok": False, "error": "nothing to undo" + (f" for {want}" if want else "")})
        if name == "ms_ws_diff":
            target = str(args.get("path") or "").strip()
            if (root / ".git").exists() and shutil.which("git"):
                if target:
                    _safe(target)
                argv = ["git", "--no-pager", "diff", "--stat", "--patch"] + (["--staged"] if args.get("staged") else []) + (["--", target] if target else [])
                try:
                    body = subprocess.run(argv, cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                                          stdin=subprocess.DEVNULL, env=_env(), **_nowin()).stdout.strip()
                except Exception as exc:
                    body = f"git diff failed: {exc}"
                if not body and not args.get("staged"):
                    st = _run("git status --short", root, 20)
                    body = "(no unstaged diff)\n" + (st.get("stdout") or "")
                return _out(body[:MAX_READ] or "no changes")
            out = []
            seen = set()
            for e in reversed(_journal()):
                if e["path"] in seen or (target and not e["path"].startswith(target)):
                    continue
                seen.add(e["path"])
                p = _safe(e["path"])
                before = (_undo_dir() / e["blob"]).read_text(encoding="utf-8", errors="replace") if e.get("blob") else ""
                after = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
                d = _diff(before, after, e["path"], 2, 6000)
                if d:
                    out.append(d)
            return _out("\n".join(out)[:MAX_READ] or "no recorded changes (not a git repo; diffs come from the undo journal)")
        if name == "ms_ws_move":
            a, b = _safe(args["from_path"], must_exist=True), _safe(args["to_path"])
            if a == root:
                return _err("cannot move the workspace root")
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(a), str(b))
            return _out({"ok": True, "from": _rel(a) if a.exists() else args["from_path"], "to": _rel(b)})
        if name == "ms_ws_delete":
            if args.get("confirm") is not True:
                return _err("set confirm=true to delete (make sure it is exactly what the user asked for)")
            p = _safe(args["path"], must_exist=True)
            if p == root.resolve():
                return _err("refusing to delete the workspace root")
            if p.is_dir():
                n = 0
                for dp, ds, fs in os.walk(p):
                    for f in fs:
                        if n < 200:
                            _backup(Path(dp) / f, "delete")
                        n += 1
                shutil.rmtree(p)
                return _out({"ok": True, "deleted": args["path"], "files": n, "undo": "ms_ws_undo (first 200 files are recoverable)" if n else None})
            _backup(p, "delete")
            p.unlink()
            return _out({"ok": True, "deleted": args["path"], "undo": "ms_ws_undo"})
        GIT_READ = {"status", "diff", "log", "show", "branch_list", "blame"}
        gated = name in ("ms_ws_run", "ms_ws_build", "ms_ws_process", "ms_ws_check") or (name == "ms_ws_git" and str(args.get("action")) not in GIT_READ)
        if gated and not s.get("allow_run") and not (name == "ms_ws_build" and args.get("step") == "detect"):
            return _err("Running commands is OFF. The user can enable 'Allow commands' in Multi-Script settings → Code & Build. Until then, write the files and tell the user the exact command to run.")
        if name == "ms_ws_run":
            cmd = str(args["command"]).strip()
            bad = _danger(cmd)
            if bad:
                return _err("refused: this command could damage the machine outside the project", pattern=bad)
            cwd = _safe(args.get("cwd") or ".", must_exist=True)
            if args.get("background"):
                logdir = _snap_dir()
                pid_id = f"p{int(time.time() * 1000) % 10_000_000}"
                log = logdir / f"{pid_id}.log"
                fh = open(log, "w", encoding="utf-8", errors="replace")
                extra = {} if os.name == "nt" else {"start_new_session": True}
                proc = subprocess.Popen(cmd, cwd=str(cwd), shell=True, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                        env=_env(args.get("env")), **extra, **_nowin())
                with _lock:
                    _procs[pid_id] = {"proc": proc, "cmd": cmd, "started": time.time(), "log": log, "fh": fh}
                time.sleep(1.5)
                return _out({"ok": True, "id": pid_id, "pid": proc.pid, "running": proc.poll() is None,
                             "early_output": _clip(log.read_text(encoding="utf-8", errors="replace"))})
            res = _run(cmd, cwd, _int(args.get("timeout_s"), 180, 1, 1800), _env(args.get("env")))
            res["command"] = cmd
            return _out(res)
        if name == "ms_ws_process":
            act = args.get("action")
            with _lock:
                items = dict(_procs)
            if act == "list":
                return _out({"ok": True, "processes": [{"id": k, "cmd": v["cmd"], "running": v["proc"].poll() is None, "exit_code": v["proc"].poll(),
                                                       "age_s": round(time.time() - v["started"])} for k, v in items.items()]})
            v = items.get(str(args.get("id") or ""))
            if not v:
                return _err("unknown process id", known=list(items))
            if act == "stop" and v["proc"].poll() is None:
                try:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(v["proc"].pid)], capture_output=True, **_nowin())
                    else:
                        import signal
                        try:
                            os.killpg(os.getpgid(v["proc"].pid), signal.SIGTERM)
                        except Exception:
                            v["proc"].terminate()
                    v["proc"].wait(timeout=5)
                except Exception:
                    v["proc"].kill()
            try:
                v["fh"].flush()
            except Exception:
                pass
            return _out({"ok": True, "id": args.get("id"), "running": v["proc"].poll() is None, "exit_code": v["proc"].poll(),
                         "output_tail": v["log"].read_text(encoding="utf-8", errors="replace")[-8000:]})
        if name == "ms_ws_build":
            kinds = detect_project(root)
            step = args.get("step")
            if step not in BUILD_STEPS:
                return _err(f"unknown step {step!r}", steps=BUILD_STEPS)
            if step == "detect" or not kinds:
                return _out({"ok": bool(kinds), "project": kinds, "hint": None if kinds else "No recognised project files. Scaffold with ms_ws_create_project or write a package.json / pyproject.toml / .csproj / Cargo.toml / go.mod / CMakeLists.txt."})
            pick = next((k for k in kinds if k["kind"] == args.get("kind")), kinds[0])
            cmd = pick.get(step)
            if not cmd:
                return _err(f"no '{step}' recipe for a {pick['kind']} project - use ms_ws_run with the exact command", recipes=pick)
            res = _run(cmd, root, _int(args.get("timeout_s"), 900 if step in ("install", "package") else 300, 5, 1800))
            res.update({"kind": pick["kind"], "step": step, "command": cmd})
            return _out(res)
        if name == "ms_ws_git":
            if not shutil.which("git"):
                return _err("git is not installed on this PC")
            act = str(args.get("action") or "status")
            paths = [str(x) for x in (args.get("paths") or []) if str(x).strip()]
            for x in paths:
                _safe(x)  # jail check
            ref = str(args.get("ref") or "").strip()
            if ref and not re.match(r"^[\w./@^~:-]+$", ref):
                return _err("ref contains unsupported characters")
            if act != "init" and not (root / ".git").exists():
                gr = _run("git rev-parse --show-toplevel", root, 10)
                if not gr.get("ok"):
                    return _err("this workspace is not a git repository", hint="ms_ws_git action=init (needs Run commands)")
            msg = str(args.get("message") or "").strip()
            argv = {
                "status": ["status", "--short", "--branch"], "diff": ["--no-pager", "diff", "--stat", "--patch"] + (["--"] + paths if paths else []),
                "log": ["--no-pager", "log", "--oneline", "--decorate", "-n", str(_int(args.get("max_count"), 15, 1, 200))],
                "show": ["--no-pager", "show", "--stat", "--patch", ref or "HEAD"], "branch_list": ["branch", "-a", "-vv"],
                "blame": (["--no-pager", "blame", "-w", "--"] + paths[:1]) if paths else None, "init": ["init"],
                "add": ["add", "--"] + paths if paths else ["add", "-A"], "commit": ["commit", "-m", msg] if msg else None,
                "branch": ["branch", ref] if ref else None, "checkout": ["checkout", ref] if ref else None,
                "stash": ["stash", "push", "-u"], "restore": ["restore", "--"] + paths if paths else None,
            }.get(act)
            if not argv:
                return _err(f"git {act}: missing parameter (paths, message or ref)")
            t0 = time.time()
            try:
                r_ = subprocess.run(["git"] + argv, cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    timeout=120, stdin=subprocess.DEVNULL, env=_env(), **_nowin())
                res = {"ok": r_.returncode == 0, "exit_code": r_.returncode, "seconds": round(time.time() - t0, 2), "stdout": _clip(r_.stdout), "stderr": _clip(r_.stderr)}
            except subprocess.TimeoutExpired:
                res = {"ok": False, "timed_out": True}
            res["command"] = "git " + " ".join(argv)
            return _out(res)
        if name == "ms_ws_check":
            kinds = detect_project(root)
            if not kinds:
                return _err("no recognised project - nothing to check", hint="ms_ws_build step=detect")
            steps = [x for x in (args.get("steps") or ["typecheck", "lint", "test"]) if x in ("typecheck", "lint", "test", "build")]
            tmo = _int(args.get("timeout_s"), 300, 10, 1800)
            report, seen = [], set()
            for k in kinds:
                for st in steps:
                    cmd = k.get(st)
                    if not cmd or cmd in seen:
                        continue
                    seen.add(cmd)
                    r_ = _run(cmd, root, tmo)
                    errs = [ln for ln in ((r_.get("stdout") or "") + "\n" + (r_.get("stderr") or "")).splitlines()
                            if re.search(r"error|fail|Traceback|exception|✗|FAILED", ln, re.I)][:15]
                    report.append({"kind": k["kind"], "step": st, "command": cmd, "ok": r_.get("ok"), "exit_code": r_.get("exit_code"),
                                   "seconds": r_.get("seconds"), "first_errors": errs, "tail": (r_.get("stdout") or "")[-1200:] if not r_.get("ok") else None})
            ok = all(x["ok"] for x in report) if report else False
            return _out({"ok": ok, "steps": report, "verdict": "all checks passed" if ok else ("no runnable check recipes" if not report else "fix the failures above and run ms_ws_check again")})
        if name == "ms_ws_http":
            import urllib.request, urllib.error
            from urllib.parse import urlparse
            url = str(args.get("url") or "")
            u = urlparse(url)
            if u.scheme not in ("http", "https") or (u.hostname or "") not in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                return _err("only http(s)://localhost or 127.0.0.1 URLs are allowed")
            if u.hostname == "0.0.0.0":
                url = url.replace("0.0.0.0", "127.0.0.1", 1)
            method = str(args.get("method") or "GET").upper()
            body = args.get("body")
            data = body.encode("utf-8") if isinstance(body, str) else (json.dumps(body).encode("utf-8") if body is not None else None)
            req = urllib.request.Request(url, data=data, method=method, headers={str(k): str(v) for k, v in (args.get("headers") or {}).items()})
            if data and not req.has_header("Content-type"):
                req.add_header("Content-Type", "application/json" if str(body).lstrip()[:1] in "{[" else "text/plain")
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=_int(args.get("timeout_s"), 15, 1, 120)) as resp:
                    txt = resp.read(400_000).decode("utf-8", errors="replace")
                    return _out({"ok": True, "status": resp.status, "ms": round((time.time() - t0) * 1000), "headers": dict(list(resp.headers.items())[:25]), "body": _clip(txt)})
            except urllib.error.HTTPError as exc:
                return _out({"ok": False, "status": exc.code, "body": _clip(exc.read(100_000).decode("utf-8", errors="replace"))})
            except Exception as exc:
                return _err(f"request failed: {exc}", hint="is the server running? start it with ms_ws_run background=true")
        if name == "ms_ws_plan":
            pp = _plan_path()
            pp.parent.mkdir(parents=True, exist_ok=True)
            try:
                plan = json.loads(pp.read_text(encoding="utf-8"))
            except Exception:
                plan = []
            act = str(args.get("action") or "show")
            items = args.get("items") or []
            if act == "clear":
                plan = []
            elif act == "set":
                plan = [{"id": i + 1, "text": str((it or {}).get("text") if isinstance(it, dict) else it)[:300], "status": (it.get("status") if isinstance(it, dict) and it.get("status") in ("todo", "doing", "done", "blocked") else "todo"), "note": ""} for i, it in enumerate(items[:40])]
            elif act == "update":
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    for row in plan:
                        if row["id"] == _int(it.get("id"), -1):
                            if it.get("status") in ("todo", "doing", "done", "blocked"):
                                row["status"] = it["status"]
                            if it.get("text"):
                                row["text"] = str(it["text"])[:300]
                            if it.get("note"):
                                row["note"] = str(it["note"])[:300]
            pp.write_text(json.dumps(plan, indent=1), encoding="utf-8")
            mark = {"todo": "[ ]", "doing": "[~]", "done": "[x]", "blocked": "[!]"}
            done = sum(1 for r_ in plan if r_["status"] == "done")
            return _out(f"Plan {done}/{len(plan)} done\n" + "\n".join(f"{mark[r_['status']]} {r_['id']}. {r_['text']}" + (f"  — {r_['note']}" if r_.get("note") else "") for r_ in plan) if plan else "Plan is empty.")
        if name == "ms_ws_snapshot":
            act = args.get("action")
            d = _snap_dir()
            if act == "list":
                return _out({"ok": True, "snapshots": sorted(x.name for x in d.glob("*.zip"))})
            if act == "create":
                label = re.sub(r"[^A-Za-z0-9_-]+", "-", str(args.get("label") or "snap"))[:40]
                dest = d / f"{time.strftime('%Y%m%d-%H%M%S')}-{label}.zip"
                n = _zip_project(dest)
                return _out({"ok": True, "snapshot": dest.name, "files": n})
            if act == "restore":
                nm = str(args.get("name") or "")
                src = d / nm
                if not nm or not src.exists():
                    return _err("unknown snapshot", snapshots=sorted(x.name for x in d.glob("*.zip")))
                with zipfile.ZipFile(src) as z:
                    for m in z.namelist():
                        target = _safe(m)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(m) as fin, open(target, "wb") as fout:
                            shutil.copyfileobj(fin, fout)
                return _out({"ok": True, "restored": nm, "note": "Files from the snapshot were written back; files created after it were left in place."})
        if name == "ms_ws_package_zip":
            nm = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(args.get("name") or root.name))
            dist = root / "dist"
            dist.mkdir(exist_ok=True)
            dest = dist / f"{nm}.zip"
            n = _zip_project(dest)
            return _out({"ok": True, "zip": _rel(dest), "files": n, "bytes": dest.stat().st_size})
    except KeyError as e:
        return _err(f"missing required parameter {e}", tool=name, schema=next((t["inputSchema"] for t in TOOLS if t["name"] == name), None))
    except (ValueError, FileNotFoundError) as e:
        return _err(str(e))
    except Exception as e:  # pragma: no cover
        return _err(f"{type(e).__name__}: {e}")
    return _err(f"unknown workspace tool {name}", tools=sorted(TOOL_NAMES - {"ms_ws_configure"}))
