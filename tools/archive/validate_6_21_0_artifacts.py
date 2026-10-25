"""Validate the 6.21.0 release archives by extraction."""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

WS = Path(r"C:/Users/Claudiu/WorkBuddy AI/2026-09-30-21-05-57")

THEMES = ["auto", "midnight", "graphite", "frost", "mono", "ink", "synthwave", "forest"]


def check(zip_path: Path, pref: str, label: str) -> int:
    z = zipfile.ZipFile(zip_path)
    names = z.namelist()
    bad = 0

    def ok(cond: bool, msg: str) -> None:
        nonlocal bad
        print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
        if not cond:
            bad += 1

    print(f"=== {label} :: {zip_path.name} ===")
    print(f"  entries: {len(names)}")

    man_name = next((n for n in names if n.endswith("extension/manifest.json")), None) \
        or next((n for n in names if n == "manifest.json"), None)
    if man_name is None:
        print("  [FAIL] manifest.json not found")
        return bad + 1
    ext_pref = man_name[: -len("manifest.json")]
    print(f"  manifest at: {man_name}")

    m = json.loads(z.read(man_name))
    print(f"  version: {m['version']} / {m.get('version_name')}")
    ok(m["version"] == "6.21.0", "manifest version is 6.21.0")
    ok(m.get("version_name") == "6.21.0 Studio", "version_name is '6.21.0 Studio'")

    blocks = m["content_scripts"]
    print(f"  content_script blocks: {len(blocks)}")
    # Assert the actual provider set rather than a magic count - a count silently
    # rots every time a provider is added (it did, twice).
    providers = sorted(
        f.split("/")[-1][:-3]
        for b in blocks for f in b.get("js", []) if f.startswith("providers/")
    )
    expected = sorted([
        "deepseek", "chatgpt-cm", "chatgpt", "claude", "gemini", "kimi", "glm",
        "arena", "meta", "qwen-net", "qwen", "notion",
    ])
    print(f"  providers: {providers}")
    ok(providers == expected, f"the {len(expected)} expected provider blocks are present")

    # Two block shapes, both deliberate:
    #  * ISOLATED core blocks: the full 12-script chain (engines..trust..main) at
    #    document_idle - these drive the agent loop.
    #  * MAIN-world taps: ONE script at document_start. chatgpt-cm.js and
    #    qwen-net.js wrap window.fetch in the PAGE world to read streamed API
    #    responses verbatim; an isolated-world wrap would not see the app's calls,
    #    so they must NOT load the core chain (and must not load trust.js).
    main_world = sorted(
        b["js"][0].split("/")[-1][:-3]
        for b in blocks if b.get("world") == "MAIN"
    )
    core_blocks = [b for b in blocks if b.get("world") != "MAIN"]
    print(f"  MAIN-world taps: {main_world}")
    ok(main_world == ["chatgpt-cm", "qwen-net"],
       "exactly chatgpt-cm and qwen-net are MAIN-world taps")
    ok(all(len(b.get("js", [])) == 1 and b.get("run_at") == "document_start"
           for b in blocks if b.get("world") == "MAIN"),
       "MAIN-world taps load exactly one script at document_start")
    ok(all("core/trust.js" in b.get("js", []) for b in core_blocks),
       f"all {len(core_blocks)} isolated core blocks load core/trust.js")
    ok(all("core/main.js" in b.get("js", []) for b in core_blocks),
       "all isolated core blocks load core/main.js")

    missing = [f for b in blocks for f in b.get("js", []) if ext_pref + f not in names]
    ok(not missing, f"no missing script refs ({missing or 'none'})")

    def read(suffix: str, must_start: str = ""):
        n = next((x for x in names if x.endswith(suffix) and x.startswith(must_start)), None)
        return (n, z.read(n).decode("utf-8")) if n else (None, "")

    # ── bridge.py: the two error-loop fixes ──────────────────────────────────
    br_name, bridge = read("runtime/bridge.py", pref)
    if br_name:
        ok("_EMPTY_STRING_IS_VALUE" in bridge,
           "bridge treats '' as a VALUE for the old_string sentinel")
        ok("_apply_documented_sentinels" in bridge,
           "bridge fills the create sentinel for multi_edit + className")
        ok(not re.search(r"'minimum':\s*8,\s*'maximum'", bridge)
           and not re.search(r'"minimum":8,', bridge),
           "no limit parameter still declares a hard minimum of 8")
        ok(bridge.count("'minimum': 1, 'maximum'") >= 6,
           "the six limit parameters declare minimum:1 (clamp, not reject)")
        ok("The limits are CLAMPED here, never rejected" in bridge,
           "the clamp-not-reject rationale is documented at the clamp")
    else:
        print("  (runtime/bridge.py not in this archive - store build)")

    # ── notion.js: the route guard ───────────────────────────────────────────
    n_name, notion = read("extension/providers/notion.js", pref)
    if n_name:
        init_body = notion[notion.index("init({ diag: d } = {})"):]
        init_body = init_body[: init_body.index("allItems, isUserItem")]
        ok("_explicitOpen" not in init_body,
           "init() does not arm the route-guard override")
        ok("function hasAiSurfaceEvidence()" in notion,
           "evidence-based AI-surface detection is present")
        ok("surfaceOk = () => isAiSurface() || _explicitOpen || hasAiSurfaceEvidence()" in notion,
           "surfaceOk() combines route + explicit open + evidence")
        ok("chosen || fallback || e.parentElement" in notion,
           "composerFrame() last resort is the editor's own parent")
    else:
        print("  (providers/notion.js not in this archive)")

    # ── Roblox plugin: the rebuilt interface ─────────────────────────────────
    lua_name, lua = read("MultiScriptCompanion.server.lua", pref)
    if lua_name:
        ver = [l.strip() for l in lua.splitlines() if "PLUGIN_VERSION = " in l]
        print(f"  plugin version: {ver[:1]}")
        ok('PLUGIN_VERSION = "6.21.0"' in lua, "Roblox plugin bumped to 6.21.0")
        ok("local T = {" in lua and "mono0=Color3.fromRGB(6,6,10)" in lua,
           "plugin carries the extension's design tokens")
        ok("local DOT_FOR = {}" in lua, "status dots are paired via DOT_FOR")
        ok("local function setReadiness(value)" in lua, "readiness bar helper present")
        ok("local function statusRow(" in lua, "status rows are built by a helper")
        ok("primaryButton" in lua and "secondaryButton" in lua,
           "both button weights exist (light primary / dark secondary)")
        ok("local savedOpen = plugin:GetSetting" in lua,
           "the panel opens on first install and remembers its state")
        ok("Run non-destructive readiness scan" in lua,
           "the scan affordance keeps its wording")
        ok("loadstring(" not in lua, "no loadstring anywhere in the plugin")
        ok("msrb_replace_script to set a whole script source" in lua,
           "the empty-old_string error names the right tool")
        for tool in ["msrb_project_summary", "msrb_patch_script", "msrb_delete_instances"]:
            ok(f"handlers.{tool}=" in lua, f"handler {tool} present")
    else:
        print("  (roblox plugin not in this archive - store build)")

    # ── CSS invariants carried forward ───────────────────────────────────────
    css_name, css = read("overlay.css", pref)
    if css_name:
        shells = re.findall(r"#zs-menu\s*\{[^}]*\}", css)
        joined = "\n".join(shells)
        ok(bool(shells) and bool(re.search(r"position:\s*fixed", joined)),
           "settings menu is still viewport-fixed")
        ok(bool(re.search(r"max-width:\s*calc\(100vw", joined)),
           "settings menu is still width-clamped to the viewport")
        chip_n = len(re.findall(r'\.zs-theme-opt\[data-theme="[a-z]+"\] i\{background:', css))
        ok(chip_n == len(THEMES), f"all {len(THEMES)} themes still have a palette chip")

    if pref:  # full build carries the sources
        ok(pref + "docs/release-notes/RELEASE_NOTES_6.21.0.md" in names, "RELEASE_NOTES_6.21.0.md present")
        ok(pref + "docs/release-notes/RELEASE_NOTES_6.20.0.md" not in names,
           "stale RELEASE_NOTES_6.20.0.md removed")
        ok(pref + "tests/test_notion_route_guard.js" in names,
           "tests/test_notion_route_guard.js present")
        ok(pref + "tools/bump_6_21_0.py" in names, "tools/bump_6_21_0.py present")

    print(f"  -> {'ALL CHECKS PASSED' if not bad else str(bad) + ' CHECK(S) FAILED'}")
    return bad


def main() -> int:
    fails = 0
    fails += check(WS / "Multi-Script-Extension-6.21.0.zip", "", "EXTENSION (store upload)")
    print()
    fails += check(WS / "Multi-Script-6.21.0-Full.zip", "Multi-Script/", "FULL")
    print()
    print("VALIDATION:", "OK" if not fails else f"{fails} FAILURE(S)")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
