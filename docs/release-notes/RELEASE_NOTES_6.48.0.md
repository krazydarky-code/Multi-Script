# Multi-Script 6.48.0 Dev

Updates now show download bytes, retry attempts and installation progress while status remains readable. Setup checks detect a mismatch between the browser extension and its registered folder. Failed checks have a bounded retry delay; interrupted installs retain recovery state and the user's previous bridge preference. Recovery validates all backups before restoring files and recognizes a completed file transaction if its final receipt was interrupted.

Chatbar controls now switch their text color immediately with the selected palette, fixing a brief low-contrast flash when moving from a light theme to a dark theme.

Ultra's Roblox GUI and animation methods were substantially rewritten using the supplied ProjectGUI, Ultraskills and UltraLab quality references. They cover native UI ownership, responsive states, focus and lifecycle, plus real rig inspection, animation ownership, markers, interruption, replication and temporal verification. Twelve existing skills now link to full scoped methods without changing the 904 skill IDs. Engine selection keeps Roblox guidance out of unrelated projects. Companion-plugin writes now receive the same relevant Ultra research and evidence checks as other project writes.

Open **Settings → Help → Updates**, check the registered folder and use **Check for updates**. When the signed release is ready, stop active sessions, save drafts, choose **Apply & reload extension**, then refresh provider tabs. If folder versions differ, run Setup from the permanent folder loaded in the browser. See [the update guide](../UPDATES.md). Browser storage and excluded private files remain in place; manual source modifications are protected.

Dev is the primary build. The Bundle still includes frozen Public 6.42.0. The Roblox Studio companion is installed separately; a browser update does not replace an already installed Studio plugin.

See [verification coverage and limits](../QA_6.48.0.md) and [Ultra reference adaptation](../ULTRA_MANUALS.md). Tests cover controlled provider/editor fixtures and real signed temporary updates; they do not certify every live account, model or editor session.
