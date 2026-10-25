# Use Multi-Script with ClickUp Brain

1. Install the current Dev extension/runtime together and reload ClickUp.
2. Sign in at `app.clickup.com` and open a **private ClickUp Brain / Ask AI conversation**, using ClickUp’s [Chat with Brain instructions](https://help.clickup.com/hc/en-us/articles/28401383762455-Chat-with-Brain). A team channel, task comment or human conversation is not a supported Multi-Script composer.
3. Open Multi-Script settings → AI providers → **Provider benchmarks** and run the local check. The composer/send control and bridge must be available. This check sends no prompt and does not certify a model response.
4. Start a new Multi-Script session. Use engine-enabled startup for connected editor work, or Code/Software mode with a permitted workspace. Follow the normal startup exchange before sending a task.
5. Begin with a small read-only task, such as listing the connected engine’s scene or retrieving a Multi-Script skill. Confirm the actual tool result, then try a reversible scratch change and read it back.

The adapter selects a visible, explicitly identified private AI panel, excluding team/chat/comment roots. It uses explicit user/assistant roles, preserves hidden command source for chips and excludes native-tool/citation content from local-command replies. A 2.5-second idle interval and a final generation check protect sends; target editor and conversation context are rechecked before typing/sending. No global human-chat submit fallback exists.

If Brain is still thinking/responding, wait or use its native Stop. If ClickUp changes the active private chat while Multi-Script prepares feedback, the send is rejected. If Send was clicked but acknowledgement is uncertain, inspect the conversation before retrying; the extension does not replay it automatically. Quotas, models and account access remain ClickUp’s controls.

If no private composer is recognized, leave human/team composers untouched, open the dedicated Brain conversation and reload. Provide sanitized diagnostics with your version and a description of the private AI layout. Do not weaken the private-scope guard to make a generic textarea work.

**Verification boundary:** the full shipped manifest chain passes deterministic ClickUp Brain fixtures with real Python catalog/skill/SVG tool execution, chips, Ultra/Critic prompts, queued follow-ups and dropped-ack protection. Additional tests cover hidden scopes, nested human previews, quiet pacing and changed-chat rejection. Live navigation reached ClickUp login; the authenticated Brain DOM/account was not inspected because live sign-in testing was declined. “Perfect compatibility” with every account layout is not claimed.

## Current Ask and model layouts

The current Ask landing placeholder, “Turn ideas into action. Create tasks, documents, or anything else with a prompt.”, and model-independent “Tell … what to do next” headings are recognized. Existing older Ask layouts remain supported. ClickUp's own model selector controls Claude, GPT, Gemini or other available models; Multi-Script does not pin Claude. The full original task stays above Ultra guidance, including with native reference attachments.

The **Super Agents** creation screen (“Describe goals, roles, tasks, or processes for your Super Agent”) configures an agent; it is distinct from an **Ask** conversation. The persistent Multi-Script bar explains that surface and directs you to Ask. It does not treat a configuration form, team chat or task comment as a private AI conversation. See ClickUp's [model selection](https://help.clickup.com/hc/en-us/articles/30802296047511-Select-an-AI-model) and [Super Agent creation](https://help.clickup.com/hc/en-us/articles/37033397273111-Create-a-Super-Agent) documentation.
