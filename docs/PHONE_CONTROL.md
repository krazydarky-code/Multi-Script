# Control Multi-Script from your phone

Updated in **6.46.0 Dev**. The frozen 6.42.0 Public companion does not include it.

## Set it up

1. Extract the current Dev build to a permanent folder. Run its Setup script, load its `extension` folder, reload your provider tabs and restart the bridge. Keep the extension and runtime on the same version.
2. Connect your phone and computer to the same trusted Wi-Fi/LAN. Keep the computer awake and its browser open.
3. On the desktop, click the small **phone icon** in the Multi-Script chatbar, or open **Settings → Co-work → Phone control**.
4. Select the computer's private network address and click **Enable on this network**. If Windows asks about Python's firewall access, allow your trusted **Private** network. Do not enable public-network access or router port forwarding.
5. Open the displayed `http://192.168.…:17615` address in your phone's ordinary browser. Use the exact address and port shown; no phone extension is needed.
6. Enter the eight-digit pairing code and a device name. Each code works once and expires after two minutes. Use **New pairing code** on the desktop if it expires.
7. Choose a provider session on the phone. Start that chat on the desktop first. For continued work in hidden tabs, enable the existing background-running option on the desktop; phone control respects it.

Guest Wi-Fi/client isolation, a VPN or a firewall can block direct communication between devices. Select the address of the adapter your phone can reach. This version supports private IPv4 LAN connections, not access over cellular or outside your network.

## What you can control

- **Task progress:** inspect the reported checklist, remaining steps, blockers, evidence and tool-result/error counts.
- **Follow-up / correction / goal:** queue instructions in the selected chat. They wait for the existing safe send boundary and never replace a desktop draft or interrupt provider generation.
- **Pause queue / Resume queue:** control queued follow-ups. Pausing the queue does not pause an already-running model response or tool.
- **Stop run:** request the existing desktop Stop action. A tool that was already dispatched may still finish; inspect its result before restarting.
- **Receipts:** distinguish queued, dispatching, acknowledged, rejected, expired and unconfirmed requests. An acknowledgement confirms the desktop action, not task completion. After a lost connection, inspect receipts and the desktop before resubmitting.

The desktop must remain connected. A chat or workspace change invalidates commands targeting its old context. Sleeping/disconnected computers disable remote controls after the last snapshot becomes stale. Account access, provider quotas, pacing and editor permissions still apply.

## Run monitor

Open **Run monitor** in Co-work or the task icon in the chatbar when a task exists. Complex tasks receive the local `ms_task_progress` tool and current run ID with their prompt. Models can report concrete steps and update them as they work. Completion requires an evidence note; reopening a step clears its previous evidence. Adding scope keeps prior steps visible.

Simple requests automatically show **Capture your request → Work on your request → Receive the final response**. A completed response only finishes these response stages; it does not certify a project. For complex tasks, the AI replaces these with a detailed task plan. A final reply or successful tool chip cannot complete unfinished reported steps.

The panel shows the current stage, remaining work and elapsed time. A rough remaining-time range uses optional AI `estimate_seconds` per step, or at least two completed steps with measured start/end times. Estimates adjust as work changes and pause on blockers, provider errors or Stop. Unknown timing stays labelled rather than inventing an ETA. Restoring an interrupted task preserves its plan and timestamps and marks it paused.

The phone receives the same task stage, reported plan and available estimate. This is a live execution checklist; it does not hold every tool until a single final execution phase.

For a ready-to-paste support post, use the [Discord phone tutorial](DISCORD_PHONE_TUTORIAL.md).

## Turn it off

On the desktop, open Phone control and **Revoke** an individual device or **Turn off remote** to close the listener and revoke every device. Pairing lasts one hour, is held in memory and is cleared when the bridge restarts. Phone control starts disabled after every bridge restart.

The remote uses HTTP on your trusted local network; traffic is **not encrypted**. Do not use untrusted/shared Wi-Fi or expose this listener to the internet. It exposes bounded task status and browser actions, not direct workspace file access or engine RPC. See [privacy](PRIVACY.md) and [security](SECURITY.md).
