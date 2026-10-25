# Multi-Script 6.42.1 Dev

Dev is now the primary edition and the only rolling release. The combined bundle
includes current Dev and unchanged Public 6.42.0. Public is a frozen companion and
does not include the latest fixes. Packaging enforces this policy with a pinned
checksum and actual manifest version checks.

The six new studio themes are tested across menu/chatbar combinations, composer
portals, docking, phone widths, persistence and full/reduced/no-motion settings.
Light-theme labels, Daybreak reading surfaces and independent bar colors have
been corrected. Ultra's animated text now follows the chatbar's light/dark theme
when it differs from the menu. See [QA evidence](../QA_6.42.1.md) for results and limits.

Install the complete Dev package, reload the extension and provider tabs, rerun
Setup for a new permanent install path and restart the bridge. Existing appearance
preferences stay in browser storage. Preserve existing private studio-data when
upgrading. Install only one edition at a time.
