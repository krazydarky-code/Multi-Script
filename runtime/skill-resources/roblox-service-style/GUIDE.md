# Multi-Script Roblox service architecture and style

Adapted from the user's supplied Roblox Lua Style Guide. Preserve existing working projects and public interfaces; this profile is not a reason to rename unrelated code. Use it for new service-based Luau work or when the user selects this style. Its naming choices are project preferences, not Roblox API rules.

## Structure and ownership
Give each game system a narrow singleton service module with private state, a small explicit interface and an init/start/stop lifecycle appropriate to that project. Put server-only services in ServerScriptService; never replicate sensitive authority or persistence logic. Shared/client modules and reusable assets may live under ReplicatedStorage, grouped by service or stable project conventions. Use one server bootstrap and one client bootstrap in the existing entry points. Initialize dependency order explicitly when it matters and avoid yielding require cycles.

Reuse existing packages for signals, networking and cleanup. Add a package only for a real repeated need; inspect its license and pinned version. Separate reusable classes from service singletons. Keep content/balance configuration authoritative and avoid independent copies of the same tunable. Preserve actual source-sync ownership: a Rojo-managed script must be edited in its source tree.

## Networking and data
Use the project's small networking wrapper rather than hand-creating duplicate RemoteEvents in the Studio tree. Requests express player intent; the server validates type, bounds, ownership, distance, cooldown and rate before consequential changes. Never trust client damage, rewards, currency or arbitrary Instance references. Keep persistence schema and keys stable, distinguish load failure from empty data, use safe atomic updates and bounded backoff, and test with isolated fixtures instead of live purchases or player data.

## UI and lifecycle
Keep a top-level client UI initializer with separate feature modules for HUD, menus and related flows. Build the actual interaction path, focus/gamepad/touch states and responsive layout. Disconnect events, cancel stale tweens/tasks and destroy owned transient instances when a feature, character or session ends. Test respawn, interruption, reset and repeated opens for duplicate listeners.

## Project naming preference
When this profile is explicitly adopted, new local identifiers use approximately 80% lowercase and 20% initial-uppercase with all remaining letters lowercase, with no underscores or ALLCAPS locals. Choose casing once at declaration and use that exact bound name consistently; never add runtime randomness or rename external contracts to satisfy a ratio. Use the nearest practical split for small scopes. Keep meaningful abbreviations: rs/Rs, repstorage/Repstorage, walkanim/Walkanim, walkanimid/Walkanimid and m1cd/M1cd. Do not expand abbreviations merely to change style. Preserve exact Roblox services, API methods/properties/classes/enums, Instance names, strings, asset paths and external interfaces. Existing project style wins unless the user requests a migration.

## Current APIs and verification
Use task.spawn/defer/delay/wait rather than legacy spawn/delay/wait, and Connect/Disconnect rather than obsolete lowercase event methods. Verify unfamiliar API signatures and execution contexts in official docs. Color3 channels are R/G/B in 0–1; fromRGB accepts 0–255. Restricted optional properties must be queried individually with pcall or omitted, not retried in a loop. Do not infer an empty place from a failed inspection. Read the exact target_file and studio_id from the live script tool schema and discovered session.

Trace caller, authoritative handler and returned state together. Use actual compiler/lint tools if installed; never claim static checks are a Studio playtest. Run the normal bootstrap, relevant failure cases, console inspection and a real viewport capture for visible changes. Use temporal evidence for animation/VFX. Mark observed checks, code review and unavailable tests separately; known defects remain unfinished work.
