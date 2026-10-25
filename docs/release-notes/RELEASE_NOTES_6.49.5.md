# Multi-Script 6.49.5 Dev

- Fix ChatGPT false pre-Send message-fidelity failures caused by rich-editor paragraph hydration. Preserve blank lines, indentation, Unicode and complete inline messages.
- Stabilize ClickUp Ask Brain detection when its greeting/placeholder changes. Support rich-editor child placeholders and heading variants; keep controls visible during remount gaps.
- Preserve strict private-AI boundaries, changed-chat/draft rejection, generation checks and no duplicate replay after uncertain Send acknowledgement.
- Retain existing Ultra manuals, skills, styles, references, native rendering and the removed workspace Render button.

Update the same permanent installation, run Setup.bat, restart the bridge, reload the extension and refresh EVERY open ChatGPT/ClickUp tab. The screenshot shows 6.49.2; existing content scripts need tab reloads to pick up this update. Saved projects and private settings should be preserved when merging the package. Authenticated provider account behavior was not live-certified in this environment.
