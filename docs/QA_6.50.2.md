# 6.50.2 verification

This patch addresses actual resource discovery, bounded task preloading, scoped Obsidian recall, PDF reference viewing and Arena streaming work. Checks exercise the native Python library, PDF rendering, actual provider content-script chain and existing regressions. Required CI covers the exact release commit; its receipt is attached to the release.

The preload makes one bounded read-only bridge request, reuses a short-lived result and preserves the original request at the top. Stop, navigation, draft and settings changes invalidate a pending send. A timeout leaves retrieval available on demand. Reference content is data, not permissions, project implementation or a claim that an image was seen.

OMNI exposes 522 entries, six reviewed source modules and four recipe sets. Screenshot previews require the original REFERENCES.pdf imported in the local vault; it is not redistributed in the extension. One PDF page is rendered in a bounded separate process. An absent reader/PDF is reported honestly. Obsidian recall isolates project notes and includes recent decisions and shared root notes.

Arena regression coverage includes long histories, thousands of streamed spans, shadow composer remounts, cached text invalidation, human-verification boundaries and real agent-loop transport fixtures. Signed-in account behavior and arbitrary future provider layouts still require live checks. No fixture result promises zero bugs.

All twelve existing manuals and 249 skills are retained. Each manual has a domain-specific resource application route, and the seed contains all 84 manual/engine variants. The existing game/asset/runtime permissions remain in force.

Provider repairs in this patch:

- GLM's current nested `.relative` text wrapper no longer hides the native Send button; the adapter locates the enclosing form.
- Gemini inserts one escaped, text-only paragraph document and normalizes line endings before native Quill reconciliation. The real Quill 2.0.3 A/B fixture reproduces the previous incomplete-prompt failure; the new path preserves CRLF, blank paragraphs, literal markup, indentation and 350 lines. Cancellation and exact complete-draft checks remain.
- ClickUp recognizes the Brain² Ask landing prompt and retains its private composer through focus and remounts. Human channels, task comments and Super Agents remain excluded.
- Kimi.ai is the canonical new-chat destination; existing legacy host permissions remain compatible.
- Startup requires a successful ordinary-JSON discovery result before reporting Session ready. A model using an unavailable native function route receives one bounded text-transport repair; persistent denial stops without replaying writes or creating a fake build-verification task.
- Venice recognizes its latest native Response failed panel even if no final assistant prose exists. Historical failures and quoted error messages are ignored; native backend failures remain visible and require provider recovery.

The public GLM, Gemini and Kimi.ai composer DOMs were inspected without sending model messages. Account-specific entitlements, authenticated ClickUp and provider backend availability were not certified. Required CI includes 150 suites plus 10 Windows native checks.

The installed 6.50.1 bridge exposed a schema-normalization bug: the refresh property injected false before context could select its fresh default. The schema now leaves this optional value unset; context refreshes by default and explicit false still requests caching. The regression warms the real index, creates an external note, runs the actual bridge argument normalizer and confirms that default context sees the new note while explicit cached context does not. The full existing resource, provider and engine suite remains required.
