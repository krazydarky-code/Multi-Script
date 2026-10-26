# Headless Blockbench assets

Settings → Engines → **Prepare Blockbench** installs a pinned, file-based MCP backend and attaches it through a real handshake, tool listing and ping. No Blockbench editor window or desktop add-on is required. Existing engine connections, custom server configuration and model files are preserved. It is an asset backend, not another game-engine session.

The optional dependency uses reviewed [blockbench-mcp-plugin v1.10.1](https://github.com/jasonjgardner/blockbench-mcp-plugin/tree/v1.10.1), checksum-pinned source/Bun and frozen npm integrity locks. Preparation requires Node/npm; normal starts are offline and do not install packages. `runtime/launch_blockbench_mcp.py` can also be configured as a stdio MCP command. Missing preparation exits with a configuration error instead of looping through downloads.

Twenty-one advertised `bbmodel_*` tools cover model inspection, cubes/meshes, UVs, embedded textures/materials, groups, animations/poses, validation and supported exports. Use each real schema; do not invent operation names or treat a file save as visual approval. Pass the current `expected_revision` on edits. The backend refuses stale edits, rolls back invalid operation batches and confines paths to its dedicated workspace under protected `runtime/studio-data/blockbench-workspace`. Ambiguous writes are never automatically replayed after a process failure.

**Prepare rendering** explicitly installs the separate frozen GPU worker. It requires Node 24+ and a compatible GPU. Normal render calls never install packages. The stable verified entry allows rendering to be prepared without restarting active model sessions. `bbmodel_render` defaults to preserving existing output files and can render an animated clip at a chosen time. Missing renderer/GPU support returns an error; preparation alone is not a rendered model.

The headless integration excludes upstream desktop-launch/model-URL tools and uses `--no-web-links`. It does not modify Blender's workspace render controls. File-based assets remain editable `.bbmodel` sources that can be opened in the Blockbench desktop app independently.

Local verification exercised the actual pinned server: 21-tool handshake, creation, editing, embedded texture assignment, animation sampling, validation, export, stale-revision refusal, rollback, path containment, concurrent attachment and an actual textured animated GPU PNG. CI runs the native file roundtrip on Linux and Windows. GPU rendering is a separate local check; arbitrary device drivers and every exporter/format are not certified by one fixture.

Source is GPL-3.0; upstream license and dependency notices remain in the prepared source cache. Multi-Script's patches and exact source/digest pins are readable in `runtime/blockbench_workspace.py`; lockfiles are under `runtime/dependencies/blockbench*`. No compiled cache or private project files ship in release archives.
