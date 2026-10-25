# Multi-Script 6.28.3

## Site refusals no longer break the loop (DeepSeek "Messages too frequent")
- New site-notice watcher: from every send on, any small notice the site adds (toast, alert, a line under your message, a short error reply) is classified as **rate limit**, **outage** or **usage cap** — in English, Chinese, French, Spanish, German, Portuguese.
- The loop now **waits the site out and re-sends the SAME message** (the tool result is never lost) instead of sending a new "busy" nudge, which was itself another message and deepened the limit. Backoff: rate 20 s → 5 min, outage 6 s → 3 min, cap 5 → 15 min. Budgets: Standard 6/5/0, Persistent 14/10/8. Own budget, not the consecutive-failure cap.
- Adaptive per-site send floor: every rate limit doubles the minimum gap between sends (8 s → 90 s), every clean tool turn decays it; saved per site. Applies even with pacing Off. DeepSeek also has a fixed 3.5 s minimum gap.
- The startup handshake gets the same recovery.
- Applies to every provider (Notion behaviour itself unchanged).

## New provider: PromptQL (prompt.ql.app)
- Open a project → New bot / thread, keep the **@Bot** chip on (Multi-Script switches it on if needed), press Start.
- Validated live: composer (tiptap), send/stop, turn detection, reply reading, "Working" phase, mention chip, thread URLs; a scripted 3-turn command loop ran cleanly.
- Site-specific rules stop the PromptQL bot from refusing the protocol or using its own data tools.
- Long messages (PromptQL stored only ~10k chars of a 27k message) are sent in parts: context parts go to the room with the bot chip off, the last part to the bot. Long tool results are paged (`more_output`).
