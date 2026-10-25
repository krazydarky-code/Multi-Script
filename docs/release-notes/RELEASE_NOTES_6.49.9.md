# Multi-Script 6.49.9 Dev — GitHub delivery restored

This release moves official source and signed updates to **krazydarky-code/Multi-Script** and includes the latest ChatGPT native-editor transport fixes. Product version remains **6.49.9**. Existing skills, Ultra manuals/styles/references, donation control, rendering and native project data are preserved.

- ChatGPT reads native rich-text documents and applies a complete draft in one checked native edit where supported. Disabled inputs retain drafts; stale same-length CodeMirror corrections are refreshed. Exact-message checks and no replay after uncertain Send remain.
- The updater retains server-requested rate-limit cooldowns across restarts and uses increasing backoff for repeated network failures. Broken or inaccessible hosting no longer becomes a rapid repeating request loop.
- Publishing is explicit opt-in, checks exact main/CI before loading signing material, serializes uploads, reuses matching draft assets, stops on API refusal and retains immutable public releases. CI is sharded without dropping existing targeted suites.
- The existing signing trust and extension identity are retained. Public 6.42.0 remains the checksum-pinned frozen companion.

**Install / one-time migration:** merge the complete Dev package into your existing permanent installation while preserving private configuration and `runtime/studio-data`. Run Setup, reload the extension and refresh every provider tab. Old feeds cannot discover a new GitHub owner when the old account is inaccessible; extension-only replacement does not update the native feed. Existing 6.49.9 builds require this manual bootstrap because their numeric version is unchanged. Later higher versions use Settings → Help → Updates.

Verification distinguishes local native/provider fixtures, real engine checks, remote CI and the public signed feed. See the repository update/delivery guides and CI receipts. No account-suspension prevention or universal bug-free guarantee is claimed.

## Earlier 6.49.9 improvements retained

# Multi-Script 6.49.9 Dev

- Remove mandatory progress planning and per-tool reporting from every effort level. Response/tool activity stays automatic. Keep a concise internal plan; explicit checklists remain available when useful or requested. Ultra keeps its specialist methods, references and verification requirements.
- Return a small receipt for checklist changes instead of echoing the whole evidence history. Full reads retain all evidence. Add atomic batched milestone updates, reject malformed/stale reports, and make unchanged plans/updates no-ops. Do not persist reads or repeated updates.
- Stop unchanged monitor paints from mutating the page. Preserve the evidence DOM while activity/timing labels change, avoid redundant persistence at tool start, and exclude extension-owned UI changes from the provider response observer.
- Replace pairwise history containment checks with ancestor membership checks. Read the current assistant once per snapshot instead of four times. Native token edits, remounts, Stop controls and generation signals stay live; no stale response cache is introduced.
- Keep large general/software catalogues compact too: discovery/retrieval schemas plus a complete direct-tool index, with exact schemas on demand. The actual 279-tool general catalogue fits one Vani reply. Progress and paging calls no longer trigger periodic tool-list reminders. Pages stay available, with instructions to retrieve only information needed for the task.
- Preserve existing skills, Ultra manuals, reference/style resources, native Blender functionality and the compact chatbar corrections. Keep actual verification boundaries; a progress receipt never certifies the whole task.

Merge into the same permanent installation while preserving private settings and runtime/studio-data. Run Setup.bat, restart the bridge, reload the extension and refresh every provider tab. Start a fresh Multi-Script session so old planning instructions do not remain active. See QA_6.49.9.md for scope.

## Same-version chatbar correction

Fix scene themes forcing action wrapping and pushing Terminal onto an orphan row when Code/Build is enabled. Keep the desktop control row intact, allow text actions to shrink with proper ellipsis, and use a tighter layout for small desktop composers. Roomy contains its complete action group when large controls need another row. Preserve all controls, theme artwork, donation, effort labels and checklist functionality. Automatic response stages and optional batched evidence-bearing checklists remain; no mandatory progress ritual returns.

This correction retains version 6.49.9 and uses a separate corrected package folder. Existing 6.49.9 artifacts are preserved. Install the corrected package manually; a version-only update feed cannot distinguish two builds with the same version. Reload the extension and every provider tab. The extension manifest version_name identifies Chatbar correction.

## Content-fit sizing correction

Restore the selected control size whenever the actual visible controls fit. Regular uses 30-pixel controls, Compact 26, and Roomy 36. Hiding/showing controls refits the same bar; extra space no longer leaves the action group permanently compressed. Roomy first tries a single row at full height, with tighter spacing if needed. Only content that cannot physically fit moves to another row.

Replace fixed width-based 24/26-pixel overrides and unconditional Roomy rows with one content-driven fit routine. It measures preferred sizing first, reserves the complete name/effort label, then compresses spacing and only necessary text actions. Regular/Compact reduce density only for genuinely crowded rows. Free/fit docks use the preferred natural width. Unchanged layout inputs reuse the fitted result rather than measuring every frame. Roomy glyphs scale with its controls. Existing themes, user visibility choices, donation, checklist functionality, native transport and saved data remain.

Version remains 6.49.9. Install this separately packaged corrected build manually in the same permanent installation, preserving private configuration and runtime/studio-data, then run Setup and reload the extension/provider tabs. Same-version builds do not appear as a newer version in a version-only updater. Prior packages remain available in their original output folders.


## Response recovery and useful local progress

Active generation is not timed out after a three-minute readable-text pause. Regression fixtures advance the wall clock past the prior cutoff with native generation active, then verify normal settlement when it ends. Native error recovery uses only the current reply's explicit Retry/Clear affordance, bounded by Error recovery and normal/shared provider pacing, with checks repeated after waits. Uncertain dispatch never repeats automatically; earlier local commands are not replayed. Off preserves manual Retry/Resume behavior.

Task progress shows bounded real tool/error/recovery activity without asking the model for progress turns. Restore, evidence retention, short receipts, unchanged-paint DOM stability and all effort policies are checked. New tests are test_response_recovery_6499.js and test_task_activity_6499.js. These are local browser fixtures, not authenticated live-provider certification. No test suite can guarantee absence of all bugs.


## Incremental application and Arena streaming cost

All effort policies direct the model to apply a coherent slice with a complete live tool call, inspect the actual result, and continue from that applied state. Script source operations through ms_roblox_script_manage are classified as writes rather than being missed by implementation tracking. Read remains read. The agent loop continues to execute each completed command before sending its feedback, rather than waiting for the final answer. Partial streaming commands are never executed.

Arena now discovers open shadow surfaces when DOM subtrees arrive instead of repeatedly scanning every document element for composer/Stop lookups. Live last-assistant reads stop at the newest matching turn instead of enumerating historical markdown. A bounded per-node text cache invalidates on native child/text edits and excludes extension chips. The performance fixture uses 400 historical turns and a 3,000-span current code block: 100 reads produce no repeated universal document scan or historical markdown query; native token replacement, chip exclusion and new shadow composers remain current. A parser/agent-loop fixture applies Luau and script-source slices before its final response, and records real tool receipts without extra progress turns. These are fixtures, not live Studio certification.


## Prompt wording comparison

A controlled old/new comparison uses the same original task, two scripted Luau command responses and final text through the shipped prompt/agent/provider transport. Both must apply slices before the final answer, preserve the original request, deliver exact tool feedback and add zero checklist turns. Six effort prompt sizes retain the existing 9,000-character fixture budget. The new wording remains selected because it explicitly orders per-slice application/result waits and removes the ambiguous task-final-reply instruction. This is a prompt/transport contract comparison, not a live-model quality or latency benchmark. Test: test_prompt_wording_ab_6499.js.

The broad legacy suite is also executed and failures compared with the previous 6.49.9 source. The release verification report distinguishes fixed regressions, inherited failures and optional native-engine environment gaps; it does not claim universal bug freedom. The full skill/manual/reference assets are retained. Actual recent execution/recovery events appear before generic response stages in the run monitor.


## Layout stability and legacy regression maintenance

Open settings menus no longer assign identical geometry every animation frame. A five-provider fixture requires zero idle style-attribute writes. Horizontal nudge parsing now accepts the browser's single-value CSS translate serialization (for example, 62px instead of 62px 0px); the writer uses the same canonical form. This removes the alternating translation/clamping feedback that moved the bar and menu. Nudge drag, reset, edge clamp and stable menu tests remain across Auto/Floating/Window docks.

The old full suite was run before maintenance and failed cases were reproduced against prior source. Legacy tests now preserve their behavioral assertions with current contracts: the donation affordance is present, fit density is content-driven, reviewed/restored specialist workflows stay distinct, catalogue counts remain 249 skills / 263 virtual tools, Notion fixture messages carry current semantic roles, startup waits follow actual lifecycle state, updates model an older loaded extension, and prompt enhancement preserves the original task above additions. No skill/manual/catalogue runtime data was rewritten to satisfy these tests. Pixel contrast sampling now actually hides Ultra's gradient foreground before sampling the surface, and the load-order DOM shim supports replaceChildren. The theme matrix also caught and fixed inherited light-menu colors on a dark bar.

Dry runs and explicitly unapplied/unacknowledged native results do not count as observed implementation. Native Retry must acknowledge actual generation or changed reply content; disappearing error chrome alone is insufficient and does not trigger another click.


Notion's intentional model-picker probe now retains the extension menu while still yielding bar click targets to native popups. General user-opened native popup behavior remains covered separately. The complete old/new prompt comparison restores both the previous transport tail and the absence of the new per-slice policy line: the new complete policy adds 67 characters (Ultra fixture 8,992 versus 8,925), within the existing budget. Both scripted transports apply two slices before final text; the new wording stays selected for clarity. It is not a live-model compliance or latency claim.

Latest receipts cover 267 unique suites after baseline comparison, product fixes and legacy-fixture maintenance. All return success; two include explicitly reported optional environment gaps (Blender bpy / Unity compile sections in the pro-tools suite, and POSIX integration on Windows). Separate real headless Blender-workspace and Godot checks pass. Authenticated live provider accounts are outside fixture certification. The final verification report lists exact receipts and limits rather than promising universal bug freedom.


Arena's optional performance observer now degrades conservatively when MutationObserver is unavailable in a restricted/minimal DOM context: provider loading and verification detection remain available, and untracked reply text is not cached. The full suite is rerun on the corrected source after the earlier broad run and focused repairs. Historical failed receipts remain available; the final report uses the final-run receipts rather than concealing failures by editing logs.
