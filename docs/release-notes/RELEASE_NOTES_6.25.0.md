## 6.25.0 — Studio UI

**Chat bar**
- Notion: the bar now docks on the *validated* composer card (painted/rounded surface that hugs the editor) instead of the first big wrapper around it. In the empty-chat layout (usage banner + tall wrapper) the bar no longer floats in the middle of the page; if no trustworthy card exists it docks directly above the editor.
- Other providers: the generic dock validates `barAnchor` and falls back to the editor when the anchor is oversized.
- Bar rebuilt: brand + one-line status (full text in tooltip), split bridge button, always-visible settings gear, four styles (Native / Card / Glass / Minimal), three sizes, tiny-width compaction, hides when the composer scrolls off-screen.
- New **Chat bar** settings tab: Position (Auto / Floating / Window), Align, Width (full/fit), nudge X/Y, Look (style, size, status line), per-item toggles, Re-align, Copy layout report, Reset.

**Menu**
- Rebuilt with a left category rail (Home, Chat bar, Agent, Notion, Look, Tools, Engines, AI sites, Help), global search, accordions for dense tabs, "Jump to" cards on Home, smoother open/close and tab transitions (respects reduced motion), scroll position preserved across refreshes, Esc to close.
- Legacy tab ids (setup / interface / appearance / studio) still map to the new tabs.

**Claude**
- Claude (claude.ai / claude.com) was already a provider. Fixed a load-order crash (`diag()` ran before its state existed, aborting the content script on claude.ai), added a mock-page regression test and a description in the AI sites list.

**Tests**: new `tests/test_chatbar_studio.js`; `test_studio_ui.js`, `test_notion_*` updated for the new information architecture.
