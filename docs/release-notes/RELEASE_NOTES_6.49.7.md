# Multi-Script 6.49.7 Dev

- Tie headless Blender workers to the owning bridge process and hold an exclusive project lock. Stop orphan workers after an owner crash, including during busy Python execution. Refuse a second writer; reopen committed native geometry after recovery.
- Validate worker startup identity and complete IPC envelopes. Terminate a worker after malformed/truncated/lost replies or timeout before permitting another operation. Preserve the selected project and never replay an uncertain edit automatically.
- Replace GLM and Kimi's unconfirmed click/Enter fallbacks with current-composer binding, remount checks, exact draft verification, awaited reference upload, cancellation, one native Send and positive acknowledgment. Ignore hidden/extension inputs and block busy user clicks from bypassing augmentation.
- Fix actual Lexical multiline reconciliation dropping Kimi's prompt prefix. Use native plain-text paste when handled by the editor, with native editing fallback and complete-document verification. Preserve user task, indentation and blank lines.
- Display every effort level beside Multi-Script. Keep the mode label visible when the name must shrink, and use two rows for crowded bars. Add a smooth keyboard/touch range, clickable stops, four Ultra palettes (Amethyst, Rainbow, Aurora, Sunset) and Live flow, Soft pulse or Static presentation. Respect reduced motion and forced colors; use darker gradients on light surfaces. Appearance changes do not alter tools or effort permissions.
- Add a glowing Ko-fi donation card to the Home panel, opening https://ko-fi.com/multixscript only when clicked.
- Turn Arena model-preference metadata off by default, including old unmarked saved defaults. An explicit new profile choice opts in; the native model picker remains in control.
- Preserve existing Ultra manuals, all 249 skill definitions, styles, references, saved-project support and automatic native rendering. The workspace Render button remains removed.

Merge into the same permanent installation while preserving private settings and runtime/studio-data. Run Setup.bat, restart the bridge, reload the extension, refresh every provider tab and reopen Blender Workspace. Start a fresh Multi-Script session to replace old scripts and tool catalogs. Authenticated provider accounts were not exposed for live certification; see QA_6.49.7.md.
