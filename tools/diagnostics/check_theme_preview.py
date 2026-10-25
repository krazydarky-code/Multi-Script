"""Sanity-check the isolated theme-grid preview used to verify the 6.18.0 fix."""
import re
from pathlib import Path

h = Path(r"C:/Users/Claudiu/WorkBuddy AI/2026-09-30-21-05-57/theme_picker_preview.html").read_text(encoding="utf-8")

THEMES = ["auto", "midnight", "graphite", "frost", "mono", "ink", "synthwave", "forest"]

checks = {
    "4-column grid rule present": "repeat(4,1fr)" in h,
    "all 8 per-theme chip rules": all(f'.zs-theme-opt[data-theme="{t}"] i{{background:' in h for t in THEMES),
    "late re-assert sets ink-2": ".zs-theme-opt {" in h and "var(--mono-ink-2)" in h,
    "grouped block uses ink-3": "color: var(--mono-ink-3)" in h,
    "no ink-4 bound to a theme pill": not re.search(r"\.zs-theme-opt[^{]*\{[^}]*var\(--mono-ink-4\)", h),
    "'before' comparison panel present": "Before 6.18.0" in h,
    "'after' panel present": "After 6.18.0" in h,
}

for name, ok in checks.items():
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

n_buttons = len(re.findall(r'<button class="zs-theme-opt', h))
print(f"  theme buttons rendered: {n_buttons} (2 panels x 8 = 16 expected)")
checks["16 theme buttons across 2 panels"] = n_buttons == 16

bad = sum(1 for v in checks.values() if not v)
print("PREVIEW:", "OK" if not bad else f"{bad} FAILURE(S)")
raise SystemExit(0 if not bad else 1)
