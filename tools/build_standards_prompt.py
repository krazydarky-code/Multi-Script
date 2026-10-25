#!/usr/bin/env python3
"""Regenerates the full always-on Roblox standards block inside extension/core/main.js from runtime/skills.json.
Run after editing any of the seven standards skills:  python3 tools/build_standards_prompt.py"""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Priority order: the exact-spec standards first, because a summary cannot replace them.
IDS = ["check-clean-ui", "check-props", "code-quality", "fix-errors", "game-systems", "npc-pathfinding", "vfx-assets"]
SKIP = ("Goal:", "Inspect the relevant live schemas once", "Use actual artifacts, logs/read-back")
skills = json.load(open(os.path.join(ROOT, "runtime", "skills.json"), encoding="utf-8"))
items = []
for sid in IDS:
    v = skills[sid]
    lines = [f"=== {sid.upper()} - use for: {v.get('whenToUse', '')}"]
    optional = v.get("ruleSections") or {}
    keep = v.get("standardsSections")  # for skills with optional sections: only these are always sent
    hidden = []
    for x in v["steps"]:
        if x.startswith(SKIP) or x == v.get("description"):
            continue
        head = x.split(":", 1)[0] if ":" in x[:60] else ""
        if keep is not None and head in optional and head not in keep:
            if head not in hidden: hidden.append(head)
            continue
        lines.append("- " + x)
    if hidden:
        lines.append("- Other sections, loaded with ms_get_skill when the request needs them: " + ", ".join(hidden) + ". Style sections (sleek modern, glass, horror, sci-fi, fantasy, minimal, retro, realistic) replace the Cartoon style when the user asks for them.")
    items.append([sid, "\n".join(lines)])
text = "\n".join(x[1] for x in items)
const = "  const MS_STANDARDS_FULL = " + json.dumps(items, ensure_ascii=True) + ";\n"
path = os.path.join(ROOT, "extension", "core", "main.js")
src = open(path, encoding="utf-8").read()
begin, end = "  // BEGIN GENERATED STANDARDS (tools/build_standards_prompt.py)\n", "  // END GENERATED STANDARDS\n"
block = begin + const + end
if begin in src:
    src = re.sub(re.escape(begin) + r".*?" + re.escape(end), lambda m: block, src, flags=re.S)
else:
    anchor = "  // Compact always-on Roblox standards"
    assert src.count(anchor) == 1, "anchor not found"
    src = src.replace(anchor, block + anchor)
open(path, "w", encoding="utf-8").write(src)
print("standards block:", len(text), "chars (~%d tokens)" % (len(text) // 4))
