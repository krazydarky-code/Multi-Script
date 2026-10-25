# DeepSeek account access and message delivery

Multi-Script 6.48.7 removes a real send-loop bug: when an image was uploading, the adapter could click Send repeatedly for up to 25 seconds. It now waits for native upload readiness, dispatches once, and requires a cleared composer or a new user turn. An uncertain acknowledgement pauses rather than replaying. Cancellation, a still-thinking reply, unsupported images, failed uploads and oversized messages stop before a new Send click. Long instructions are rejected rather than silently cut.

DeepSeek uses your configured pacing and the existing shared-tab send coordination. The fixed 20-second minimum and six-turn rolling cap added in 6.48.6 are removed. Their saved synthetic state is migrated, while actual provider cooldowns, reset hints, account pauses and live send leases remain. Reload the extension and refresh all provider tabs to use the current worker and adapter. Pacing cannot guarantee account access.

Automatic error recovery is Off for DeepSeek, even when a saved global recovery setting is Persistent. A busy reply, rate limit, failed/empty reply or parse failure does not trigger recovery prompts. Initialization supports up to six read-only discovery results, including catalog followed by Studio discovery. Automatic native Continue clicks are disabled too; inspect a truncated reply before continuing manually. Actual task tool/result messages continue normally within the traffic limits. Ultra task instructions, tool permissions and stored effort settings are preserved.

Visible native account suspension, termination, restriction and verification notices stop sending. Generated model prose about account restrictions does not count as a native notice. These safeguards cannot prove why DeepSeek restricted an account, guarantee future account access, restore an account, or make unauthorized automation permitted. Prompt wording is not an account-protection mechanism. Do not repeatedly restart after an access notice; resolve the restriction with DeepSeek first.

For an account that is already restricted, use DeepSeek's own appeal/contact route. Their official FAQ discusses risk-control account restrictions and their terms provide a Contact Us route. For programmatic workloads, use an officially supported API or agent integration with its own credentials, billing and limits. Multi-Script's website adapter is not the official API and does not inherit API quotas. No API migration or new API credential is configured by this release.

Primary references checked 23 October 2026:

- [DeepSeek Terms of Use](https://cdn.deepseek.com/policies/en-US/deepseek-terms-of-use.html): behavior review, risk filtering, account restrictions and contact route.
- [DeepSeek official FAQ](https://api-docs.deepseek.com/faq/).
- [DeepSeek API Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/): API concurrency and 429 handling; these are not website quotas.

Verification uses the actual shipped adapter in headless Chromium, native-shaped upload/send fixtures, the actual persistent pacing module and the full content-script chain. Tests cover one image click, dropped acknowledgements, overlapping callers, cancellation, quiet reasoning, notice boundaries, exact prompt preservation, cross-tab/restart budgets, provider independence, bounded startup/discovery, retained Ultra payloads and no automatic error replays. No live DeepSeek account was used or subjected to repeated traffic. These tests establish software behavior, not immunity from account restrictions.
