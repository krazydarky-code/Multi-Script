# Multi-Script 6.22.0 — "Studio"

One vocabulary that drives every engine, a terminal in the chat bar that starts the bridge for you,
and the JSON-schema error class closed for good.

---

## The JSON-schema errors: fixed at the class, not the instance

The loop you kept hitting was always the same shape:

> *ERROR calling '<tool>': invalid parameters: parameters.<field> …*

Every single one was **a schema that advertised a constraint stricter than the handler
accepted**. The bridge validated what the schema *said*, and the schema disagreed with what the
code underneath actually *did*. Which instance you hit depended only on which engine you had open —
which is exactly why it felt like "no matter the engine".

Fixing the reported instances by hand was never going to be enough, so this release fixes the
*category*:

- **`tools/schema_audit.py`** loads the real bridge, pulls **every** declared schema out of
  `BUILTIN_TOOLS` / `COMPANION_TOOLS` and their lookup maps, and runs the **actual validator**
  against each one. It does not grep for suspicious words — it calls the same
  `_normalize_tool_arguments` your tool calls go through.
- It flags the specific defects that cause this loop:
  - a **positive `minimum > 1`** on a count-like field (`limit`, `max`, `count`, `depth`, `steps`,
    `rounds`) — the `ms_studio_director` class, where the handler clamps but the schema rejects;
  - **inverted bounds** (`minimum` above `maximum`);
  - required string fields that must be allowed to be empty;
  - and it proves the `multi_edit` empty-`old_string` create path still passes, on every run.
- **260 schemas audited. 0 high-severity findings. 0 sentinel drift.** `--strict` exits non-zero the
  moment that stops being true, so a regression cannot ship.

The remaining real instance it found was `ms_surface_read`: the schema demanded `limit >= 500`, and
`background.js` **ignored `msg.limit` entirely** and always read the maximum. A caller asking for a
small read was rejected for a limit the worker never looked at. Both sides now agree, and the schema
says what actually happens: *any value is accepted and clamped into 200..12000.*

**The principle, now enforced everywhere: clamp, never reject.** Schemas are a superset of handler
behaviour.

---

## Native tools on all four engines — without inventing any

The honest finding first, because it changes what "add more tools" can mean: **Godot's 14 tools and
Unity's 34 tools are the complete published upstream sets.** "More native tools" cannot mean more
upstream names — those do not exist, and inventing them would produce the exact "unknown tool"
failure we were trying to eliminate.

What was actually missing is that **each engine speaks a different dialect for the same intent**, so
a model had to learn four vocabularies and got them wrong:

| Intent | Roblox | Unity | Godot | Blender |
|---|---|---|---|---|
| read the scene | `search_game_tree` + `studio_id` + `datamodel_type` | `manage_scene{action:"get_hierarchy"}` | `get_project_info{projectPath}` | `get_scene_info` |
| create an object | `execute_luau` | `manage_gameobject{action:"create"}` | `add_node{nodeType,nodeName,parentNodePath}` | `execute_blender_code` |
| write a script | `multi_edit{file_path,edits}` | `create_script{path,contents}` | *(no tool — disk)* | `execute_blender_code` |

**Six new engine-neutral tools** join the direct set (230 → **236**), and they really execute:

- **`ms_native_capabilities`** — what the connected engine can do *right now*: its live tool
  catalogue, which tools the facade has a correct wrapper for, and what is therefore unavailable.
  Call it once per session instead of guessing.
- **`ms_native_read`** — `what` ∈ tree / state / console / project / script / object.
- **`ms_native_write`** — `what` ∈ script / node / scene / properties / code, with `dry_run`.
- **`ms_native_verify`** — a fingerprint plus an explicit **CHANGED / UNCHANGED** verdict. Proof, not
  a claim.
- **`ms_native_batch`** — ordered steps, each tool name checked against the **live** catalogue,
  stopping at the first failure with a per-step report.
- **`ms_native_debug`** — diagnoses "invalid parameters" and "unknown command" and reports how
  `studio_id` resolved.

**The translation never guesses.** Every emitted call is validated against what the server
*actually advertises*; anything unsupported is a **structured refusal** (`{"ok": false, "reason": …}`)
— never an exception, never an invented name. Roblox place-scoped calls with no resolvable
`studio_id` are refused *before* anything is issued, and two connected Studios are never guessed
between, because a write to the wrong place is silent data loss.

### Six dialect bugs found and fixed during the play-test

Running the translation against the vendored upstream references — not against my memory of them —
caught six real defects:

1. **Unity `create_script` used `uri`/`content`.** It takes **`path`/`contents`**. (`find_in_file`
   legitimately takes `uri`, which is exactly the trap.)
2. **Unity object creation called `manage_scene{action:"create_object"}`.** That action **does not
   exist** — GameObjects come from `manage_gameobject{action:"create"}`.
3. **Unity scene creation had no folder**, so scenes landed somewhere unpredictable. Now
   `Assets/Scenes/`.
4. **Godot `add_node` passed the parent as `nodeName`** — naming the new node after its parent, or
   the scene path after the `.tscn`. `nodeName` is the **new** node; the parent belongs in
   **`parentNodePath`**.
5. **Roblox dot-paths did not walk.** `game:FindFirstChild("Workspace.Door")` looks for one child
   literally called that and returns `nil`, so a path that plainly exists reported "target not
   found". Now each segment is walked.
6. **Generated code was safe only by coincidence.** The Lua and Python setters joined property names
   into a quoted literal. An identifier filter blocked breakout — but the quoting *depended* on the
   filter. Both now `json.dumps` the value, so the two protections are independent.

Every one of these is now pinned by a test that fails if it comes back.

---

## The terminal icon: a live view of the bridge, inside the extension

There is a new **terminal button** in the Multi-Script chat bar. It themes itself with everything
else — accent, light/dark, backdrop — and it is a **live** readout of the bridge: green when
connected, amber and pulsing while starting, red when down.

Clicking it opens a **terminal panel directly under the icon** — a top-down menu showing exactly
what the bridge is doing, right there in the chat. No second window, no separate tool.

### What the panel shows

- **A live log stream.** Every line the bridge writes — engine connects, MCP handshakes, tool
  calls, errors — arrives as it happens, colour-coded by level, with a filter bar
  (`All / Info / OK / Warn / Error`).
- **The service chips.** One chip per engine server, showing whether it is up and how many tools
  it advertises, refreshed from the bridge's own snapshot.
- **A truthful status dot and pill** — `live` / `partial` / `offline` — driven by the real
  connection state, never by a guess.
- **Copy / Clear / Follow.** Clear empties the *view ring*, never the file on disk — the
  `bridge_debug.log` stays complete.
- **Autoscroll that respects you.** The panel only follows new lines while you are already at
  the bottom, so scrolling up to read history is never yanked away.

### How the panel stays live through a reconnect

Two channels, one renderer:

1. **The authenticated WebSocket** (preferred). The bridge keeps a bounded ring buffer
   (`deque(maxlen=600)`) with a monotonic sequence number, and pushes new records to every
   subscribed socket in batched frames. On reconnect the panel resumes **by cursor**, so nothing
   is replayed and nothing is skipped.
2. **A loopback HTTP fallback** on port `17614` (`GET /logs?since=N`). When the socket is quiet the
   panel polls this instead, so the dot and the service chips stay truthful mid-reconnect.

### Why the panel shows you the command instead of spawning it

**A content script has no process API.** That is a browser guarantee, not a limitation to route
around — a page that could spawn a process would be a page that could spawn anything. So rather
than pretend, the panel's **Start bridge** action puts the real `start.bat` command on your
clipboard, explains the limitation in one plain line, and then **watches for the bridge to answer**,
toasting the moment it comes up. It never claims to have started something it did not.

*This is why the previous release's `start_launcher.bat` / `bridge_launcher.py` pair is gone.*
That design needed a second always-on localhost process with a token file and a pairing handshake —
a whole control plane — to work around a browser rule. Showing the command is simpler, has no
attack surface, and cannot get out of sync with the bridge it is describing.

---

## Notion alignment

The bar was anchored to the wrong box. Three coordinated fixes:

- **`composerFrame()` now picks the AI card.** It scores candidates by closeness to
  `editorWidth + 40` (the card's 20px padding on each side) instead of accepting the first match —
  so it no longer resolves a page column wrapped around the composer.
- **A provider-derived `barInset()`.** Notion's AI card has ~20px of internal inset and a large
  corner radius; the generic `9px 16px` bar sat visibly inside it. Notion now reports its real inset,
  and **Meta** got the same mechanism so the fix is uniform rather than a one-off.
- **The core actually applies it.** `placeBar()` consumes the inset in anchored mode — the missing
  link that had left the provider method dead code.

A test section fails if the frame resolves to the 960px column instead of the 656px card.

---

## Everything else

- **`_schema_risk_analysis`** — high-severity shape defects are now reported rather than assumed.
- **Dead code removed** from the Roblox `studio_id` resolver.
- **`ms_native_write` gained a documented `name` field** for the new node/scene, so naming a new
  object no longer means inheriting the target path.
- **`tools/bump_6_22_0.py`** and **`tools/validate_6_22_0_artifacts.py`** (57 assertions) so this
  release's invariants are checked, not remembered.

## Verification

| Suite | Result |
|---|---|
| Python (`tests/test_*.py`) | **33 passed, 0 failed** |
| JS (`tests/*.js`) | **45 passed, 0 failed** |
| Facade + terminal panel (`test_native_facade.py`) | **101 assertions passed** |
| Schema audit | **260 schemas, 0 high-severity, 0 sentinel drift** |
| 6.22.0 artifact validator | **57 assertions passed** |

Eight Python tests had pinned the literal `230` direct-tool count and failed on a *correct* build.
They now name the base and the facade add-on explicitly — so a tool silently vanishing still fails
loudly, which is the invariant they were protecting in the first place.
