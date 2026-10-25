# Multi-Script 6.32.2 — enhanced prompt sending

- Clear a previous turn's stale Stop flag before submitting a newly accepted enhanced/original prompt. Previously, the send loop attempted nothing and silently returned.
- A new Stop or conversation navigation during prompt review cancels that submission. Cancel/Escape still send nothing; a concurrent task leaves the draft in place with an explanation.
- Includes the 6.32.1 creative-tool optional-label and unique-filename fixes, plus all existing themes/providers.

Update the extension and reload provider tabs. For an upgrade from 6.32.0 or older, also update and restart the bridge to receive the creative-tool fix. Preserve runtime/config.json and custom settings.
