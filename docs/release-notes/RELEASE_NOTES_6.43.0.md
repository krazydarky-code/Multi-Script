# 6.43.0 Dev — Task progress and phone control

- A separate run-monitor dock and Co-work entry show concrete task steps, remaining work, blockers and evidence. The new local `ms_task_progress` tool binds reports to the current chat/workspace run, preserves existing scope and requires evidence before reported completion. Tool success never fills the checklist automatically.
- Optional phone control pairs an ordinary mobile browser over your trusted local IPv4 network. View supported provider sessions, inspect progress, queue follow-ups/corrections/goals, pause/resume the queue and request Stop through the existing guarded desktop actions.
- Phone remote starts disabled. Explicit desktop enablement, short-lived one-use codes, one-hour in-memory device sessions, device revocation, stale-context rejection and acknowledgement receipts bound access. The engine bridge remains loopback-only; the separate HTTP listener exposes no engine/file RPC.
- The run monitor follows Multi-Script's theme and motion preferences, fits narrow screens and closes competing settings panels. The chatbar retains its existing compact controls.
- Dev remains the current build. The combined bundle includes the unchanged checksum-pinned 6.42.0 Public companion.

[Setup and behavior](../PHONE_CONTROL.md) · [Executed checks and limits](../QA_6.43.0.md). Physical phone/Wi-Fi pairing and live authenticated provider behavior remain separate from the automated desktop/phone browser tests.
