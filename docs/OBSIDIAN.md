# Obsidian vault and bridge memory

Run `Setup.bat`, `MacOS_Setup.command` or `Setup.sh` from the complete installation. Setup creates **Multi-Script Memory** beside `extension/` and `runtime/`, seeds the versioned library, and connects that vault to this installation's bridge. Every PC uses its own installation root; no publisher-specific user path ships in the package. The native setup receipt is written only after both the launcher and vault succeed.

The file backend works without an Obsidian app, subscription, API token, REST plugin or language-model service. To browse it in Obsidian, use **Open folder as vault** and select this folder. Obsidian stores notes and attachments as ordinary files; cloud synchronization is a separate choice. See [Obsidian's vault/sync guide](https://obsidian.md/help/Getting%20started/Sync%20your%20notes%20across%20devices).

Setup seeds all 249 instruction skills, current builtin schemas, all twelve Ultra manuals with six engine playbooks each, and the reviewed OMNI catalogue/modules/recipes. These are reference snapshots, not additional skills or claims that an engine is connected. The compressed seed is under 1 MB; large PDFs, videos, images and original archives remain in the vault. Library generations retain earlier and edited pages.

The bridge advertises `ms_obsidian`:

- `status` reports the configured folder and its availability.
- `search` returns bounded indexed text from the chosen project's notes and optionally shared library/reference notes. Project identifiers are matched literally, including underscores. `refresh=true` picks up external edits immediately; ordinary searches reuse a short index cache. Searches use the active library snapshot; archives=true explicitly includes preserved older generations.
- `read` reads a bounded relative note or returns a small PNG/JPEG reference image. Large/binary attachments return metadata and an Obsidian URI. Reading a video/archive does not execute it or claim transcription/understanding.
- `remember` stores a durable project note, deduplicates identical content and preserves edited files. It adds no mandatory progress, output or memory setup turn.

Settings → Engines → **Obsidian memory vault** reconnects a moved/synced vault or imports an explicit local file. Root selection and imports require the trusted extension controls; model-generated commands cannot read arbitrary external paths or change vault configuration. Original archives are preserved as data and never executed. Imports are streamed and content-hashed, with duplicate files reused. Private project notes do not spill into another project's search.

The vault, index, configuration, notes and media are excluded from Git/release archives. Signed updates preserve the whole `Multi-Script Memory` folder, including case variants on Windows. The index can be rebuilt from ordinary notes and is kept under protected `runtime/studio-data`; it is not a cloud database. Existing browser graph memory remains available separately. Mem0 and Codebase Memory are not dependencies.

If setup fails, it reports the exact filesystem issue and preserves existing notes. You can set `MS_OBSIDIAN_VAULT` to a writable dedicated folder before setup, or reconnect a folder in settings. A configured vault that disappears is reported unavailable; normal recall/write does not silently replace it. Sync clients, storage limits and external conflicts remain governed by the chosen sync service. Back up valuable originals.
