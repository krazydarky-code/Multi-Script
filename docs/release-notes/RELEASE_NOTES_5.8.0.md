# Multi-Script 5.8.0 — Notion Always-On

- Covers notion.ai, notion.so, and notion.com, including www variants and redirects.
- Keeps a visible Multi-Script recovery bar even before Notion mounts its AI composer.
- Adds an Open Notion AI chat action and automatically attaches when the composer appears.
- Detects current textarea, contenteditable, ProseMirror, Slate, role=textbox, and open Shadow DOM composer variants.
- The extension popup can safely re-inject Multi-Script into a stale Notion SPA tab after an install/update without duplicate injection.
- Preserves prompt-only model routing and native Notion workspace behavior.
