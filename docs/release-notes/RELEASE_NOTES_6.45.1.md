# Multi-Script 6.45.1 Dev

This is the first build configured for the official GitHub update feed and pinned
publisher signing key. After one manual upgrade, users can check/download signed
updates in Settings → Help → Updates, then apply/reload when sessions are idle.
Settings, private configuration and custom studio data stay in place.

Repository publishing is automated: successful CI on the exact current main
commit builds Dev/bundle, preserves the frozen Public companion, signs the Dev
ZIP, verifies draft asset hashes and publishes the release/feed together. Private
keys remain outside source and in an Actions secret. Public releases are never
overwritten by the helper; older workflows cannot downgrade latest.

This release also publishes the preceding Ultra/skills, co-work, provider,
theme, Figma, phone and progress work that was previously only in local Dev ZIPs.
Ultra includes 12 specialist manuals, five engine playbooks and detailed craft,
style/reference/critique methods applied through the existing 904 skill contracts.
These are in-context methods; they do not train model weights.

Install **Dev**, rerun Setup, reload the extension and refresh provider tabs.
Back up your old folder and preserve private runtime/config.json during this
first manual upgrade. Keep the same browser profile; never uninstall to update.

[User/update guide](../UPDATES.md) · [Executed release QA](../QA_6.45.1.md).
Provider fixtures do not certify every authenticated account/model or native editor.
