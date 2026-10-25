# Multi-Script 6.49.1 Dev

- Wait for Gemini’s actual native completion before executing its command or sending a follow-up. Frozen text alone no longer causes a false send failure while Gemini is still answering.
- Show startup stages and elapsed time; click or keyboard-activate the startup status for details. No estimated time is invented.
- Launch Blender Workspace from the chatbar cube icon or extension popup. Keep the advanced engine-settings shortcut.
- Add Multi-Script controls inside the local Blender window: choose a provider tab, inspect reported task steps, open its chat/settings, queue a follow-up or stop the run.
- Reuse the existing context, draft, generation and dispatch-receipt safeguards. Workspace tabs receive exact-origin grants; arbitrary localhost pages cannot use the session relay.

Install in the same permanent folder, preserve private config/studio-data, run Setup.bat, restart the bridge and reload the extension/provider tabs. Reopen Blender Workspace from Multi-Script to connect its session controls. The Blender engine cache is reused.
