# OMNI methods in Multi-Script 6.50.0

This is an adaptation of the user-supplied OMNI archive. It extends the existing skills and Ultra GUI, VFX and animation methods. It does not replace them or add a competing global framework.

Use `ms_roblox_omni` only when relevant to the requested work:

- `references`: search the 522-entry compressed catalogue by query/style/id, returning at most eight entries. Every entry retains its original source metadata. The 500 screenshot studies and 22 quantified entries are approximate design references, not licensed reusable game assets or proof of behavior.
- `analyze`: compare relevant references and approximate token starting points with the project's existing primary style. Keep structural choices coherent; introduce a texture or effect accent deliberately.
- `recipe`: read a bounded UI, VFX, pose or combined composition specification. These are design recipes, with illustrative pseudocode and asset names. Implement missing behavior and verify asset permissions; they are not a catalogue of finished components.
- `modules`: discover or read six reviewed Luau modules. `Maid` owns cleanup; `Signal` owns subscriptions; `Spring` provides scalar/vector analytic motion; `Tokens` resets independent defaults; `ThemeRegistry` registers explicit themes; `Toolkit` provides native panels, wired buttons, modal/backdrop/focus handles, progress bars and finite quality-scaled cosmetic bursts.
- `install`: performs a real Roblox Luau execution call and returns its receipt. It creates a fresh namespace under ReplicatedStorage, preserves existing objects, and checks source readback. Requiring the modules creates no GUI, remotes, combat service, polling loop or global singleton. Create only the screens/effects needed for the task from a LocalScript; destroy the returned UI/cleanup handles when finished.
- `bundle`: returns the same namespaced installer source without executing it. A bundle is not an installation or playtest.

For illustrated icon/button sheets, textured panels, flipbooks and richer UI builders, use the existing `ms_forge` tool. Keep generated artwork local unless upload is needed and authorized by the task. Resolve all missing upload IDs before installing builders. Preserve the returned generation/module names; earlier generations are retained. Demo scenes are opt-in (`demo=true`).

For production: apply useful increments during the task, read back the changed hierarchy/source, connect actions to the existing authoritative data/controller, and exercise actual narrow/desktop, long-text, focus, respawn, interruption and low-quality behavior. A successful source install is not evidence that those paths passed. Do not add mandatory bookkeeping/manual-reading turns.

The original ZIP, its nested backup and 510-page PDF remain unchanged outside the release. The release uses one compressed catalogue instead of duplicate PDF/CSV/Luau catalogues. Unfinished controllers, fake verification, invented texture paths, empty template directories and unsolicited combat/network scaffolding are excluded. Recipe specifications remain available as design data. See `SOURCE.json` for provenance.
