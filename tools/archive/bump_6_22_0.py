"""Bump Multi-Script 6.21.0 -> 6.22.0 across every versioned surface.

Idempotent: running twice is a no-op on the second pass. Only touches the
literal version strings; semantic content is left alone.

6.22.0 is the "NATIVE FACADE + IN-CHAT LAUNCH" release:
  * six engine-neutral ms_native_* tools that translate one vocabulary into
    each engine's real dialect (Roblox / Unity / Godot / Blender),
  * the chat bar's terminal icon, which starts the bridge from inside the page
    via runtime/bridge_launcher.py instead of a separate start.bat,
  * Notion alignment + the schema-vs-handler sweep.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = "6.21.0"
NEW = "6.22.0"
OLD_NAME = "6.21.0 Studio"
NEW_NAME = "6.22.0 Studio"

EDITS: dict[str, list[tuple[str, str]]] = {
    "extension/manifest.json": [
        ('"version": "6.21.0"', '"version": "6.22.0"'),
        ('"version_name": "6.21.0 Studio"', '"version_name": "6.22.0 Studio"'),
    ],
    "extension/providers/notion.js": [
        ('dataset.zsNotionVer = "6.21.0"', 'dataset.zsNotionVer = "6.22.0"'),
    ],
    "roblox-plugin/MultiScriptCompanion.server.lua": [
        ('local PLUGIN_VERSION = "6.21.0"', 'local PLUGIN_VERSION = "6.22.0"'),
    ],
    "runtime/bridge.py": [
        ('BRIDGE_VERSION = "6.21.0"', 'BRIDGE_VERSION = "6.22.0"'),
    ],
    "runtime/elevenlabs_audio.py": [
        ("Multi-Script/6.21.0", "Multi-Script/6.22.0"),
    ],
    "runtime/engine-compatibility-audit.json": [
        ('"release": "6.21.0"', '"release": "6.22.0"'),
    ],
    "runtime/product-manifest.json": [
        ('"version": "6.21.0"', '"version": "6.22.0"'),
    ],
    "README.md": [
        ("# Multi-Script 6.21.0", "# Multi-Script 6.22.0"),
        ("Multi-Script-6.21.0.zip", "Multi-Script-6.22.0.zip"),
        ("Multi-Script Bridge v6.21.0", "Multi-Script Bridge v6.22.0"),
    ],
    "extension/README.md": [
        ("# Multi-Script browser extension 6.21.0", "# Multi-Script browser extension 6.22.0"),
        ("Multi-Script-Extension-6.21.0.zip", "Multi-Script-Extension-6.22.0.zip"),
    ],
    "docs/ROBLOX_PLUGIN.md": [
        ("Multi-Script 6.21.0 includes", "Multi-Script 6.22.0 includes"),
    ],
    "tests/test_roblox_companion.py": [
        ('PLUGIN_VERSION = "6.21.0"', 'PLUGIN_VERSION = "6.22.0"'),
        ('"pluginVersion": "6.21.0"', '"pluginVersion": "6.22.0"'),
        ('status["bridgeVersion"] == "6.21.0"', 'status["bridgeVersion"] == "6.22.0"'),
    ],
    "tests/test_product_manifest_plugin_613.py": [
        ('m["version"]=="6.21.0"', 'm["version"]=="6.22.0"'),
        ('PLUGIN_VERSION = "6.21.0"', 'PLUGIN_VERSION = "6.22.0"'),
    ],
    "tools/build_release.py": [
        ("VERSION='6.21.0'", "VERSION='6.22.0'"),
    ],
    "tools/release_check.py": [
        ('VERSION="6.21.0"', 'VERSION="6.22.0"'),
        ("docs/release-notes/RELEASE_NOTES_6.21.0.md", "docs/release-notes/RELEASE_NOTES_6.22.0.md"),
        ("missing 6.21.0 release notes", "missing 6.22.0 release notes"),
    ],
    "runtime/critic-loop-report.json": [
        ('"version": "6.21.0"', '"version": "6.22.0"'),
        ("PASS Multi-Script 6.21.0 release check", "PASS Multi-Script 6.22.0 release check"),
    ],
    # The launcher carries its own independent version: it is a separate process
    # that can be updated on its own, so it must NOT track the bridge's number.
}

SWEEP = [
    "docs/release-notes/RELEASE_NOTES_6.21.0.md",
]


def main() -> int:
    touched: list[str] = []
    problems: list[str] = []

    for rel, subs in EDITS.items():
        p = ROOT / rel
        if not p.is_file():
            problems.append(f"missing {rel}")
            continue
        src = p.read_text(encoding="utf-8")
        out = src
        for old, new in subs:
            if old in out:
                out = out.replace(old, new)
            elif new not in out:
                problems.append(f"{rel}: neither {old!r} nor {new!r} present")
        if out != src:
            p.write_text(out, encoding="utf-8")
            touched.append(rel)

    old_notes = ROOT / f"docs/release-notes/RELEASE_NOTES_{OLD}.md"
    new_notes = ROOT / f"docs/release-notes/RELEASE_NOTES_{NEW}.md"
    if old_notes.is_file():
        body = old_notes.read_text(encoding="utf-8")
        new_notes.write_text(body.replace(OLD, NEW), encoding="utf-8")
        old_notes.unlink()
        touched.append(f"docs/release-notes/RELEASE_NOTES_{NEW}.md (renamed)")

    # Guard: no stale literals may survive anywhere that matters. Provenance
    # banners in bridge.py record WHEN a tool group landed, not the current
    # version, so they are intentionally preserved.
    ALLOW = {
        "runtime/bridge.py",
        "tools/bump_6_22_0.py",
        "tools/bump_6_21_0.py",       # earlier releases' own bump scripts
        "tools/bump_6_18_0.py",
        "tools/bump_6_17_8.py",
        "tools/validate_6_21_0_artifacts.py",
        "tools/validate_6_18_0_artifacts.py",
        "CHANGELOG.md",
        # release/ holds the PREVIOUS build's output. It is regenerated from
        # scratch by build_release.py, so it must keep the version it was built
        # at until the next build overwrites it.
        "release/release-manifest.json",
        "release/SHA256SUMS.txt",
    }
    stale: list[str] = []
    for pat in ("*.json", "*.py", "*.js", "*.md", "*.html", "*.lua"):
        for p in ROOT.rglob(pat):
            parts = set(p.parts)
            if "node_modules" in parts or ".git" in parts:
                continue
            rel = p.relative_to(ROOT).as_posix()
            if p.name.startswith(f"RELEASE_NOTES_{OLD}"):
                continue
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if OLD not in txt:
                continue
            if rel in ALLOW:
                if rel == "runtime/bridge.py":
                    offenders = [
                        ln.strip() for ln in txt.splitlines()
                        if OLD in ln and not ln.lstrip().startswith("#")
                    ]
                    if offenders:
                        stale.append(f"{rel} (non-comment: {offenders[:2]})")
                continue
            stale.append(rel)

    print(f"touched ({len(touched)}):")
    for t in sorted(touched):
        print("  " + t)
    if problems:
        print("PROBLEMS:")
        for x in problems:
            print("  " + x)
    if stale:
        print(f"STALE {OLD} leftovers:")
        for x in sorted(stale):
            print("  " + x)
    print("OK" if not problems and not stale else "REVIEW")
    return 0 if not problems and not stale else 1


if __name__ == "__main__":
    raise SystemExit(main())
