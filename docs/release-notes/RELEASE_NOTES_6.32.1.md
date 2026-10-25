# Multi-Script 6.32.1 — creative-tool argument hotfix

- Texture names are optional; pattern stays required. UI mockup and sound-effect output labels are also optional; sound descriptions stay required.
- Unnamed texture/UI SVGs receive unique filenames instead of overwriting a shared default file. Explicit filenames retain their existing behavior.
- Texture seed 0 is preserved instead of silently becoming 1.
- Tool listings explicitly identify required parameters, and texture instructions include a minimal valid call.
- No engine target, file path, code or other essential input is invented. All existing themes and provider adapters remain included.

## Update

Use the Full bundle: update both extension and runtime files, preserve runtime/config.json and custom settings, restart the running bridge, reload the extension and provider tabs, then refresh the chat's tool catalogue or start a new chat. Updating only extension files leaves the old bridge validator running.

JSON Schema defaults are annotations, not automatic value insertion: https://json-schema.org/understanding-json-schema/reference/annotations . The optional label is handled explicitly by the generator.
