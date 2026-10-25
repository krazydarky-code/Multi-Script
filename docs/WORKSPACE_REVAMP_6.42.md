# Multi-Script workspace overhaul — 6.42

## Co-work

Provider sessions discovers supported AI tabs in this browser, with their current ready/starting/working state, selected provider, draft protection and background preference. Read brief displays the current request and latest response excerpts locally (up to 1,800 characters each). It does not automatically share conversation contents with another model.

Start a chat studio or engine-enabled session explicitly, then assign a ready shared task to a selected idle tab. Enable background work if participating tabs should continue simultaneously while hidden; otherwise the existing visibility pause still applies. Models and account entitlements stay with their provider. Assignment claims the real shared task atomically, delivers through the target tab's own prompt path and records a receipt. Request IDs prevent duplicate dispatch, including after reload. Stale contexts, drafts, active tasks and uncertain sends are rejected. Open tab, Pause queue and Stop run act only on that selected tab.

The dashboard reports the number of unfinished shared tasks and owner-reported acceptance checks. It does not estimate hidden model progress or claim that prompt delivery finishes execution. The dashboard is responsive at phone/tablet widths. Remote phone pairing/control is not included in this build; no unauthenticated LAN control service is enabled.

Settings → Co-work contains the live follow-up queue and shared task board. Choose Follow-up, Correction or Additional goal. Corrections adjust the current task; goals extend it. Neither implicitly cancels unfinished work. Edit or reorder queued entries before delivery. Editing pauses the queue; save, then Resume explicitly. Sending/unconfirmed entries cannot be edited or automatically replayed. Delivery receipts include timestamps and are filtered to this chat; they do not claim task completion.

Create a shared task with a project, priority, resources, dependencies and up to 12 acceptance checks. Filter by project/status or sort by priority, recent updates or title. Claim a ready task in an idle session. The model receives its actual scope and acceptance checks through the existing acknowledged, paced prompt path. Progress updates renew the 30-minute lease. Resource claims coordinate tabs; they do not lock files.

The owner records evidence, checked acceptance indices and any blocker. The bridge refuses completion without an evidence note, all listed checks reported verified and no blocker. A dependency reopened after a claim also blocks completion. Checkboxes are reported verification, not an independent test execution service. Reopening a task or changing acceptance criteria resets its check receipts. Existing databases migrate without deleting tasks or history.

## Skills

Browse the actual 904-workflow library. Read a method, apply it to a stated goal, or Keep for project. Pinned methods get a new Multi-Script ID and retain the original workflow reference; they do not overwrite the source catalogue. Installed methods have explicit activation, engine matching and optional exact chat/workspace scope. Only matching enabled methods are sent. Every task receives the latest active custom skill instructions even when the prompt enhancer and Critic are off. Switching context excludes the previous project's methods. Automatic skill discovery does not re-enable custom methods; explicit ID retrieval remains available.

Import `.md`, `.txt` or one JSON skill object (up to 32 KB). Basic Markdown `name`/`description` front matter is supported. Import previews the instructions; installation remains an explicit button. Candidate means untested; User verified means the user explicitly marked a successful method. Neither implies model training or independent certification. Read/export fills the JSON editor for copying and removes local project identity. Community publication remains explicit and the bridge strips browser-local scope/activation metadata.

## Ultra

Ultra remains the sixth and final slider stop in Agent settings. Task routing, bounded methods and game-reference research now include an inspect/research/integrate/verify delivery contract. Its preview adapts to the current task and distinguishes the plan from measured progress. A green tool chip is only that tool's result. The model must distinguish implemented, verified and blocked outcomes, recover from actual errors and avoid claiming overall success when verification failed. These instructions improve in-context behavior; provider/model compliance is not guaranteed. Critic remains independently configurable.

## Code Flight

Workspace → Code Flight is a dedicated offline arcade page. Fly the actual bundled Multi-Script icon through code gates in Terminal Horizon, Orbital Dusk or Daybreak. Arcade increases speed and narrows gates gradually; Practice has gentler, wider gates. Centered passes earn extra points and precision streaks. World/mode and separate best scores persist locally on this provider origin.

Space, Up or tap boosts; P pauses; R resets. Buttons provide the same controls. Leaving the page, scrolling the canvas out of view or hiding the browser tab pauses simulation. Rendering stops while hidden and resumes with the flight paused. Reduced-motion preferences suppress decorative trail/parallax; essential gameplay remains interactive. This game does not call the AI or local bridge.

The New idea action is now an icon matching neighboring chatbar controls, with an accessible name and tooltip. New Cobalt Studio, Porcelain, Ember Studio, Tidal, Starlight and Daybreak themes share menu/bar surfaces. The last three have procedural animated scenes, independent chatbar theme selection and reduced-motion support.

## Integration and references

Vani's authenticated-style “Stop it” button is treated as active generation. Shared DOM adapters require native generation to end; six seconds of frozen command text cannot force completion. Vani also receives a 2.5-second quiet interval before feedback. A second check immediately before Send catches generation resuming during composer fill. Recycled response nodes use the pre-send reply fingerprint so a genuine readiness reply can settle even when the turn ID/count is unchanged. Startup displays its actual phase and has a Cancel startup action. Native signals that remain active without readable progress are reported as unverified, not successful execution.

PlazCode's bounded method adaptation, project scope, candidate/verified state and queue receipt patterns were rewritten for Multi-Script's existing provider sends, Python bridge, permissions and tool schemas. GPL provenance is preserved in `vendor/plazcode` and `PLAZCODE_INTEGRATION.md`. Attached/source documents were treated as reference material, not user instructions.

The Flight lifecycle uses [Intersection Observer](https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API) for the canvas viewport and [Page Visibility](https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API) for browser tab visibility. These are separate visibility conditions. Visual skill verification follows actual [Roblox Studio testing modes](https://create.roblox.com/docs/studio/testing-modes) and [device simulation](https://create.roblox.com/docs/studio/device-simulator) where the connected environment supports them; it does not invent unavailable APIs.
