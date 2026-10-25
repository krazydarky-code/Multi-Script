"""Validate the 6.18.0 release archives by extraction."""
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

    # The store build flattens extension/* to the archive root (manifest.json
    # must sit at the top for Chrome). The full build nests it as
    # <root>/extension/manifest.json. Resolve rather than assume.
    man_name = next(
        (n for n in names if n.endswith("extension/manifest.json")),
        None,
    ) or next((n for n in names if n == "manifest.json"), None)
    if man_name is None:
        print("  [FAIL] manifest.json not found")
        return bad + 1
    # Everything extension-relative shares this prefix.
    ext_pref = man_name[: -len("manifest.json")]
    print(f"  manifest at: {man_name}")

    m = json.loads(z.read(man_name))
    print(f"  version: {m['version']} / {m.get('version_name')}")
    ok(m["version"] == "6.18.0", "manifest version is 6.18.0")
    ok(m.get("version_name") == "6.18.0 Anchor", "version_name is '6.18.0 Anchor'")

    blocks = m["content_scripts"]
    print(f"  content_script blocks: {len(blocks)}")
    ok(len(blocks) == 11, "11 content_script blocks")
    ok(sum(1 for b in blocks if "core/trust.js" in b.get("js", [])) == 9,
       "9 blocks load core/trust.js")

    if "permissions" in m:
        perms = sorted(m["permissions"])
        print(f"  permissions: {perms}")
        ok(perms == ["activeTab", "scripting", "storage", "tabs"], "expected 4 permissions")

    missing = [f for b in blocks for f in b.get("js", []) if ext_pref + f not in names]
    ok(not missing, f"no missing script refs ({missing or 'none'})")

    # The store build flattens extension/* to the archive root; the full build
    # keeps extension/ nested. Resolve by suffix within the extension prefix.
    css_name = next(
        (n for n in names if n.endswith("overlay.css") and n.startswith(pref)),
        None,
    )
    if css_name is None:
        print("  [FAIL] overlay.css not found in archive")
        return bad + 1
    print(f"  overlay.css at: {css_name}")
    css = z.read(css_name).decode("utf-8")

    grid = re.search(r"\.zs-theme-grid\{([^}]*)\}", css)
    cols = re.search(r"grid-template-columns:repeat\((\d+),1fr\)", grid.group(1)) if grid else None
    ok(bool(cols) and cols.group(1) == "4", "theme grid is a 4-column layout")

    chip_n = len(re.findall(r'\.zs-theme-opt\[data-theme="[a-z]+"\] i\{background:', css))
    print(f"  per-theme palette chip rules: {chip_n}")
    ok(chip_n == len(THEMES), f"all {len(THEMES)} themes have a palette chip")

    # The theme-picker legibility regression fixed in the previous release:
    ink4_on_theme = re.search(r"\.zs-theme-opt[^{]*\{[^}]*var\(--mono-ink-4\)", css)
    ok(ink4_on_theme is None, "--mono-ink-4 is not bound to .zs-theme-opt")

    reassert = re.search(r"\.zs-theme-opt \{[^}]*var\(--mono-ink-2\)", css)
    ok(bool(reassert), "late re-assert sets --mono-ink-2 on .zs-theme-opt")

    # ── 6.18.0: the settings popover must be viewport-fixed and clamped. ─────
    # Every #zs-menu shell rule; the FIRST one is the base declaration.
    shells = re.findall(r"#zs-menu\s*\{[^}]*\}", css)
    base = shells[0] if shells else ""
    ok(bool(re.search(r"position:\s*fixed", base)),
       "settings menu shell is position:fixed (viewport-anchored)")
    ok(bool(re.search(r"max-width:\s*calc\(100vw", base)),
       "settings menu clamps its width to the viewport")
    ok(not any(re.search(r"position:\s*(relative|absolute)", s) for s in shells),
       "no #zs-menu rule reverts it to flow positioning")
    ok(bool(re.search(r"#zs-root\s+#zs-menu\s*\{[^}]*min\(var\(--ms-menu-width\)", css)),
       "studio width rule clamps to the viewport")

    lua_name = next(
        (n for n in names if n.endswith("MultiScriptCompanion.server.lua")),
        None,
    )
    if lua_name is not None:
        lua = z.read(lua_name).decode("utf-8")
        ver = [l.strip() for l in lua.splitlines() if "PLUGIN_VERSION = " in l]
        print(f"  plugin version: {ver[:1]}")
        ok('PLUGIN_VERSION = "6.18.0"' in lua, "Roblox plugin bumped to 6.18.0")
    else:
        print("  (roblox plugin not in this archive — store build)")

    if pref:  # full build carries the sources
        ok(pref + "runtime/form_craft.py" in names, "runtime/form_craft.py present")
        ok(pref + "tests/test_theme_picker_legibility.js" in names,
           "tests/test_theme_picker_legibility.js present")
        ok(pref + "docs/release-notes/RELEASE_NOTES_6.18.0.md" in names, "RELEASE_NOTES_6.18.0.md present")
        ok(pref + "docs/release-notes/RELEASE_NOTES_6.17.7.md" not in names,
           "stale RELEASE_NOTES_6.17.7.md removed")
        # 6.18.0 menu-popover regression probe ships with the release.
        ok(pref + "tools/render_menu_probe.js" in names,
           "tools/render_menu_probe.js present")

    print(f"  -> {'ALL CHECKS PASSED' if not bad else str(bad) + ' CHECK(S) FAILED'}")
    return bad


def main() -> int:
    fails = 0
    fails += check(WS / "Multi-Script-Extension-6.18.0.zip", "", "EXTENSION (store upload)")
    print()
    fails += check(WS / "Multi-Script-6.18.0-Full.zip", "Multi-Script/", "FULL")
    print()
    print("VALIDATION:", "OK" if not fails else f"{fails} FAILURE(S)")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
