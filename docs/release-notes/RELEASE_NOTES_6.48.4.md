# Multi-Script 6.48.4

- Merge the supplied v24 release as the catalog base: preserve all 241 skill definitions and the shared policy; keep the removed skills out. Correct catalog/virtual-tool accounting and reload shared policy changes.
- Gemini reads all answer segments outside thinking, excludes hidden alternate replies and clipboard editors, preserves multiline/indented drafts, waits for quiet thinking, and supports native Stop response controls. Failed image uploads and cancelled large prompt insertion cannot click Send.
- Yield the toolbar when native model, effort or settings menus overlap it, keeping their click targets and layout intact.
- Restore ordinary native user messages for Adaptive, Quick, Standard, Deep, Maximum and Ultra. Remove method display chips, transcript height/visibility overrides and receipt persistence.
- Remove the cosmetic receipt request from the actual send path. A stalled cosmetic storage callback previously prevented an effort-enhanced user task from being sent; this was reproduced on the complete prior runtime.
- Keep effort instructions, enabled skills, Critic preferences and current task run IDs in the transmitted payload. Ultra demotes immediately when a lower effort is selected.
- Preserve tool/result chips, quiet-thinking protections, truthful failed startup, current composer detection and rounded toolbar styling.

Reload the extension and refresh every provider tab after installation. Already loaded older content scripts keep running until those tabs are refreshed. The full method text will be visible again in the original message.

Local tests use reduced provider layouts and deterministic model replies. They do not certify every signed-in site variant or provider service availability. GitHub publication remains blocked by the suspended publishing account; local packages are available separately.
