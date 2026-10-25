# Release notes — Multi-Script 6.33.0 — Halloween remake, terminal fix, icons

- Remade Halloween themes (Scream, Myers, Slender, Jason): layered gradient atmospheres, gradient header and tabs, inset active rails, stronger background art.
- Fixed `ReferenceError: ensureTerm is not defined` thrown by background message handlers (terminal panel, bridge idle paint) because they lived outside the UI closure.
- Regenerated extension icons (16/32/48/128) from the real Multi-Script SVG.
- Verified headlessly: the extension is loaded unpacked in Chromium against a mock provider page and every one of the 25 themes is applied and measured with 0 page errors.

# Multi-Script 6.32.2 — enhanced prompt sending
