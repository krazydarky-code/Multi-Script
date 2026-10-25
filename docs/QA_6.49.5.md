# Multi-Script 6.49.5 verification

The supplied ChatGPT screenshot identifies an exact-draft failure before Send. The previous 6.49.4 adapter reproduces that error when a native contenteditable draft is hydrated into equivalent paragraphs containing empty paragraphs. The new composer-specific serializer preserves those blank lines; the reply/code extractor remains separate. Tests cover Unicode, indentation, consecutive blank lines, CRLF and true changed-draft rejection. A supplemental local check uses actual ProseMirror EditorView/state/schema and real Chromium editing to compare the native document with a 103-line source prompt. These establish reproducible compatibility cases, not authenticated ChatGPT account certification.

ClickUp fixtures exercise the supplied Ask Brain landing pattern, greeting/placeholder removal, child-paragraph placeholders, input locks, empty AI panels beside a live private composer, H3 headings, editor detachment and remount, route invalidation and human-channel revocation. The bar persists during an editor gap, while tool sends still require an identified private AI composer. Team channels and task comments remain excluded.

The shipped full core/runtime roundtrips exercise startup, catalog/skill retrieval, actual Python-created SVG assets, queued followups and no automatic replay after an uncertain clicked Send. Transport/browser matrices cover shared DOM adapter regressions. Final receipts record actual outcomes and any skips. Signed local upgrade checks preserve private settings and saved project bytes. Existing Ultra methods, original skill definitions and native Blender rendering are retained.

Authenticated provider pages were not exposed in the available browser inventory; no claim of signed-in live-site verification is made. Public publishing remains blocked by the previously confirmed suspended GitHub account.

Editor semantics reference: https://github.com/ProseMirror/prosemirror-model/blob/master/src/from_dom.ts and https://github.com/ProseMirror/prosemirror-view/blob/master/src/input.ts. The supplemental editor dependency lock is retained in the local QA workspace and is not a user runtime dependency.
