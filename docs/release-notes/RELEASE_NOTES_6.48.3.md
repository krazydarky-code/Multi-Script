# Multi-Script 6.48.3

- Fix the cause of square/unstyled Auto-dock buttons: layout resets preserve CSS custom properties.
- Mount ChatGPT outside its complete native form so native model/voice controls keep their grid rows.
- Keep idle Task progress and compact Chat studio available. Narrow bars wrap controls instead of clipping primary actions.
- Read ChatGPT role-tagged/article transcript variants, deduplicate nested turns, exclude native actions and collapsed thinking, and preserve multiline text.
- Gemini waits for its Stop control throughout quiet thinking and refuses another send before changing the draft. Icon aliases, hidden-editor rejection and multiline extraction improve transport.
- Gemini's explicit native error pauses startup/execution. A timeout or unreadable startup cannot report ready. Discovery status distinguishes receiving a local result from waiting for the next model response.
- Remove the static Gemini unstable badge; actual detected failures remain actionable.

Local fixture/runtime checks do not certify every authenticated account/model variant or fix provider-side failures. Use the provider's Retry when its service fails. GitHub publishing requires restored account access.
