# Multi-Script 6.49.7 verification

## Headless Blender lifecycle

New actual Blender 4.5.15 LTS Windows tests kill a bridge owner during an unfinished bpy edit. A second worker is refused while the first holds its project lock. The orphan exits independently after owner death; a fresh worker reacquires the lock and reopens committed geometry without the unfinished edit. Ownership uses a pinned Windows process handle or POSIX parent identity, not a reusable PID lookup alone. No thread runs bpy outside its existing main thread.

Fault injection supplies truncated JSON, malformed JSON, scalar/invalid envelopes, native process death and a timeout during mutation. The manager loses verified status, stops the worker, retains the project and refuses automatic replay. Explicit recovery reopens the same committed model and clears stale errors. Existing native/browser integration checks retain real edits, rollback, material preview, animation, Cycles output, exports, HTTP isolation, standalone resume and tool aliases. User project files are not used for mutations.

## Provider delivery and native editors

Full shipped GLM/Kimi content chains exercise startup, real Python catalog and skill retrieval, actual SVG asset creation, Ultra/Critic delivery, queued follow-ups and uncertain-result acknowledgment without replay. Additional Chromium cases cover hidden duplicate editors/controls, same-frame remount, a delayed native Send, long Unicode/blank-line drafts, native reference upload, busy interception and cancellation. Existing provider matrices and Claude/ChatGPT/ClickUp roundtrips test shared code.

An actual Lexical 0.52.0 editor reproduction exposed dropped leading paragraphs with the old multiline execCommand path. Native text-paste fixes it; both native EditorState and adapter readback match a short prompt and a 34,849-character / 263-line prompt. Lexical is a local QA dependency only. These native editor tests do not certify an authenticated Kimi deployment's exact library version or layout.

## Appearance and defaults

Browser checks cover every effort label, range keyboard actions, fill state, clickable stops, animation/palette persistence, light/dark styling, reduced motion, forced colors, the Ko-fi destination and brand-column clipping. Visual captures were inspected. Existing composer/docking checks retain actual non-overlap in one- or two-row layouts, stable placement, native composer preservation and replacement. Tests were updated to measure two-dimensional non-overlap and bar-relative spacing, rather than assuming one row. An old customization test's section boundary and expired trial-promotion assertion were corrected to cover the current universal settings and workspace/plan boundary.

Arena tests cover clean defaults, migration from old unmarked selections, explicit opt-in/out, unchanged tool-result text, comparison pacing and no fabricated model selection. Existing manual/skill/tool suites verify catalogue coherence and retention. Final signed local upgrade receipts verify private settings and real saved model bytes from three genuine previous archives.

Signed-in provider accounts were not exposed in the available browser inventory. Test models/native responses are deterministic fixtures; actual runtime/editor/Blender results are identified separately. No claim of perfect compatibility, zero remaining bugs or successful public publication is made. GitHub publication remains blocked by the previously confirmed suspended publisher account.

Primary design/behavior references: https://academy.claude.com/tutorials/choosing-the-right-effort-level-in-claude-code (interactive effort controls; Multi-Script retains its own effort semantics), https://www.kimi.com/en/help/new-user-guide/overview (native chat/files/models), and the pinned Lexical packages' source in the local QA workspace. No native model setting is impersonated by appearance or effort controls.
