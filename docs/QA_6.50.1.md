# 6.50.1 verification

This patch addresses actual resource discovery, bounded task preloading, scoped Obsidian recall, PDF reference viewing and Arena streaming work. Checks exercise the native Python library, PDF rendering, actual provider content-script chain and existing regressions. Required CI covers the exact release commit; its receipt is attached to the release.

The preload makes one bounded read-only bridge request, reuses a short-lived result and preserves the original request at the top. Stop, navigation, draft and settings changes invalidate a pending send. A timeout leaves retrieval available on demand. Reference content is data, not permissions, project implementation or a claim that an image was seen.

OMNI exposes 522 entries, six reviewed source modules and four recipe sets. Screenshot previews require the original REFERENCES.pdf imported in the local vault; it is not redistributed in the extension. One PDF page is rendered in a bounded separate process. An absent reader/PDF is reported honestly. Obsidian recall isolates project notes and includes recent decisions and shared root notes.

Arena regression coverage includes long histories, thousands of streamed spans, shadow composer remounts, cached text invalidation, human-verification boundaries and real agent-loop transport fixtures. Signed-in account behavior and arbitrary future provider layouts still require live checks. No fixture result promises zero bugs.

All twelve existing manuals and 249 skills are retained. Each manual has a domain-specific resource application route, and the seed contains all 84 manual/engine variants. The existing game/asset/runtime permissions remain in force.
