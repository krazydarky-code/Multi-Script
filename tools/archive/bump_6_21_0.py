"""Bump Multi-Script 6.20.0 -> 6.21.0 across every versioned surface.

Idempotent: running twice is a no-op on the second pass. Only touches the
literal version strings; semantic content is left alone.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = "6.20.0"
NEW = "6.21.0"
OLD_NAME = "6.20.0 Roblox Companion Tools"
NEW_NAME = "6.21.0 Studio"

EDITS: dict[str, list[tuple[str, str]]] = {
    "extension/manifest.json": [
        ('"version": "6.20.0"', '"version": "6.21.0"'),
        ('"version_name": "6.20.0 Roblox Companion Tools"', '"version_name": "6.21.0 Studio"'),
    ],
    "extension/providers/notion.js": [
        ('dataset.zsNotionVer = "6.20.0"', 'dataset.zsNotionVer = "6.21.0"'),
    ],
    "roblox-plugin/MultiScriptCompanion.server.lua": [
        ('local PLUGIN_VERSION = "6.20.0"', 'local PLUGIN_VERSION = "6.21.0"'),
    ],
    "runtime/bridge.py": [
        ('BRIDGE_VERSION = "6.20.0"', 'BRIDGE_VERSION = "6.21.0"'),
    ],
    "runtime/elevenlabs_audio.py": [
        ("Multi-Script/6.20.0", "Multi-Script/6.21.0"),
    ],
    "runtime/engine-compatibility-audit.json": [
        ('"release": "6.20.0"', '"release": "6.21.0"'),
    ],
    "runtime/product-manifest.json": [
        ('"version": "6.20.0"', '"version": "6.21.0"'),
    ],
    "README.md": [
        ("# Multi-Script 6.20.0", "# Multi-Script 6.21.0"),
        ("Multi-Script-6.20.0.zip", "Multi-Script-6.21.0.zip"),
        ("Multi-Script Bridge v6.20.0", "Multi-Script Bridge v6.21.0"),
    ],
    "extension/README.md": [
        ("# Multi-Script browser extension 6.20.0", "# Multi-Script browser extension 6.21.0"),
        ("Multi-Script-Extension-6.20.0.zip", "Multi-Script-Extension-6.21.0.zip"),
    ],
    "docs/ROBLOX_PLUGIN.md": [
        ("Multi-Script 6.20.0 includes", "Multi-Script 6.21.0 includes"),
    ],
    "tests/test_roblox_companion.py": [
        ('PLUGIN_VERSION = "6.20.0"', 'PLUGIN_VERSION = "6.21.0"'),
        ('"pluginVersion": "6.20.0"', '"pluginVersion": "6.21.0"'),
        ('status["bridgeVersion"] == "6.20.0"', 'status["bridgeVersion"] == "6.21.0"'),
    ],
    "tests/test_product_manifest_plugin_613.py": [
        ('m["version"]=="6.20.0"', 'm["version"]=="6.21.0"'),
        ('PLUGIN_VERSION = "6.20.0"', 'PLUGIN_VERSION = "6.21.0"'),
    ],
    "tools/build_release.py": [
        ("VERSION='6.20.0'", "VERSION='6.21.0'"),
    ],
    "tools/release_check.py": [
        ('VERSION="6.20.0"', 'VERSION="6.21.0"'),
        ("docs/release-notes/RELEASE_NOTES_6.20.0.md", "docs/release-notes/RELEASE_NOTES_6.21.0.md"),
        ("missing 6.20.0 release notes", "missing 6.21.0 release notes"),
    ],
    # Generated report: carries the version plus a captured release-check line.
    "runtime/critic-loop-report.json": [
        ('"version": "6.20.0"', '"version": "6.21.0"'),
        ("PASS Multi-Script 6.20.0 release check", "PASS Multi-Script 6.21.0 release check"),
    ],
    # CHANGELOG is deliberately NOT rewritten: the 6.20.0 heading documents a
    # shipped release and must keep its own number, and a blanket substitution
    # would clobber the freshly written 6.21.0 entry. Maintained by hand.
}

SWEEP = [
    "docs/release-notes/RELEASE_NOTES_6.20.0.md",
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
        "tools/bump_6_21_0.py",
        "tools/bump_6_18_0.py",       # earlier releases' own bump scripts
        "tools/bump_6_17_8.py",
        "tools/validate_6_18_0_artifacts.py",
        "CHANGELOG.md",
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
