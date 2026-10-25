"""Bump Multi-Script 6.17.8 -> 6.18.0 across every versioned surface.

Idempotent: running twice is a no-op on the second pass. Only touches the
literal version strings; semantic content is left alone.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = "6.17.8"
NEW = "6.18.0"
OLD_NAME = "6.17.8 Legible"
NEW_NAME = "6.18.0 Anchor"

# (relative path, exact text substitutions)
EDITS: dict[str, list[tuple[str, str]]] = {
    "extension/manifest.json": [
        ('"version": "6.17.8"', '"version": "6.18.0"'),
        ('"version_name": "6.17.8 Legible"', '"version_name": "6.18.0 Anchor"'),
    ],
    "extension/README.md": [
        ("# Multi-Script browser extension 6.17.8", "# Multi-Script browser extension 6.18.0"),
        ("Multi-Script-Extension-6.17.8.zip", "Multi-Script-Extension-6.18.0.zip"),
    ],
    "README.md": [
        ("# Multi-Script 6.17.8", "# Multi-Script 6.18.0"),
        ("Multi-Script-6.17.8.zip", "Multi-Script-6.18.0.zip"),
        ("Multi-Script Bridge v6.17.8", "Multi-Script Bridge v6.18.0"),
    ],
    "release/release-manifest.json": [
        ('"version": "6.17.8"', '"version": "6.18.0"'),
        ("Multi-Script-6.17.8-Full.zip", "Multi-Script-6.18.0-Full.zip"),
        ("Multi-Script-Extension-6.17.8.zip", "Multi-Script-Extension-6.18.0.zip"),
    ],
    "runtime/bridge.py": [
        ('BRIDGE_VERSION = "6.17.8"', 'BRIDGE_VERSION = "6.18.0"'),
    ],
    "runtime/elevenlabs_audio.py": [
        ("Multi-Script/6.17.8", "Multi-Script/6.18.0"),
    ],
    "runtime/engine-compatibility-audit.json": [
        ('"release": "6.17.8"', '"release": "6.18.0"'),
    ],
    "runtime/product-manifest.json": [
        ('"version": "6.17.8"', '"version": "6.18.0"'),
    ],
    "tests/test_product_manifest_plugin_613.py": [
        ('m["version"]=="6.17.8"', 'm["version"]=="6.18.0"'),
        ('PLUGIN_VERSION = "6.17.8"', 'PLUGIN_VERSION = "6.18.0"'),
    ],
    "tests/test_roblox_companion.py": [
        ('PLUGIN_VERSION = "6.17.8"', 'PLUGIN_VERSION = "6.18.0"'),
        ('"pluginVersion": "6.17.8"', '"pluginVersion": "6.18.0"'),
        ('status["bridgeVersion"] == "6.17.8"', 'status["bridgeVersion"] == "6.18.0"'),
    ],
    "tools/build_release.py": [
        ("VERSION='6.17.8'", "VERSION='6.18.0'"),
    ],
    "tools/release_check.py": [
        ('VERSION="6.17.8"', 'VERSION="6.18.0"'),
        ("docs/release-notes/RELEASE_NOTES_6.17.8.md", "docs/release-notes/RELEASE_NOTES_6.18.0.md"),
        ("missing 6.17.8 release notes", "missing 6.18.0 release notes"),
    ],
    "roblox-plugin/MultiScriptCompanion.server.lua": [
        ('local PLUGIN_VERSION = "6.17.8"', 'local PLUGIN_VERSION = "6.18.0"'),
    ],
    # Tooling that pins the release it was written for. These are dev-only
    # validators/probes, not shipped surfaces, but they carry the literal and
    # would otherwise trip the stale guard below.
    "tools/check_theme_preview.py": [
        ("6.17.8", "6.18.0"),
    ],
    "tools/render_theme_preview.js": [
        ("6.17.8", "6.18.0"),
    ],
    "tests/test_theme_picker_legibility.js": [
        ("6.17.8", "6.18.0"),
    ],
    # CHANGELOG is deliberately NOT rewritten here: the release 6.17.8 heading
    # documents a shipped release and must keep its own number. A "## 6.17.8"
    # -> "## 6.18.0" substitution would also clobber the freshly written
    # 6.18.0 entry, so the changelog is maintained by hand.
}

# Files that carry the version only inside prose/notes; swept generically.
SWEEP = [
    "docs/release-notes/RELEASE_NOTES_6.17.8.md",
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

    # Rename the release-notes file itself.
    old_notes = ROOT / f"docs/release-notes/RELEASE_NOTES_{OLD}.md"
    new_notes = ROOT / f"docs/release-notes/RELEASE_NOTES_{NEW}.md"
    if old_notes.is_file():
        body = old_notes.read_text(encoding="utf-8")
        body = body.replace(OLD, NEW)
        new_notes.write_text(body, encoding="utf-8")
        old_notes.unlink()
        touched.append(f"docs/release-notes/RELEASE_NOTES_{NEW}.md (renamed)")

    # Guard: no stale literals may survive anywhere that matters.
    # `# ── ... (6.17.8) ──` provenance banners in bridge.py are historical
    # markers recording WHEN a tool group landed, not the current version,
    # so they are intentionally preserved.
    ALLOW = {
        "runtime/bridge.py",     # provenance banner only (asserted below)
        "tools/bump_6_18_0.py",
        "tools/bump_6_17_8.py",  # the previous release's own bump script
        "tools/validate_6_17_8_artifacts.py",  # previous release's validator
        "CHANGELOG.md",          # historical "## 6.17.8" heading is intentional
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
                # For bridge.py, every remaining hit must be a comment banner.
                if rel == "runtime/bridge.py":
                    offenders = [
                        ln.strip()
                        for ln in txt.splitlines()
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
