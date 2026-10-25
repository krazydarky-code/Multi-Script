# Multi-Script updates — 6.49.9

## For users: install this configured build once

Download the Dev ZIP or Bundle from the [official latest release](https://github.com/krazydarky-code/Multi-Script/releases/latest). Dev is the current build; the bundled Public 6.42.0 companion stays frozen.

1. Stop Multi-Script sessions and the bridge. Back up your current complete Multi-Script folder.
2. Extract Dev and copy its contents into your existing permanent Multi-Script folder, replacing release files. Keep the same folder and browser profile; do not uninstall the extension or delete the old folder first.
3. Restore your private `runtime/config.json` from your backup after copying. Keep your `.env`, engine preferences, studio-data and custom state; these are excluded from release packages. Do not restore old program files.
4. Run Setup from this updated folder. Reload Multi-Script on the browser’s Extensions page, then refresh provider tabs. Check that bridge and extension both report 6.49.9 and your themes, skills and connections remain present.

The old versions cannot discover a repository or signing key they never contained. This one-time manual upgrade supplies the official feed and public key. Ordinary users never need a GitHub login, signing key or publisher tools.

## Later updates: inside Multi-Script

Open **Settings → Help → Updates**. With automatic checks enabled, Multi-Script checks daily while the browser is running and stages a verified release. You can also click Check for updates.

The panel stays responsive while checking, downloading and installing. It reports verified download bytes, retry attempts and installed file counts when available; an unknown total stays indeterminate. A failed automatic check starts at a 15-minute retry delay, increases exponentially up to one day, and does not count as a successful daily check. Server-directed cooldowns survive native-host/browser-worker restarts. Rate-limit Retry-After/reset headers are respected; inaccessible 401/403/404/410 hosting is deferred for 24 hours instead of repeatedly queried. Network retries are bounded and respect supported short Retry-After delays. Status checks do not start another installation.

When a new version is ready, stop active Multi-Script sessions across provider tabs, save drafts and resolve queued/unconfirmed prompts. Click **Apply & reload extension**, then refresh provider tabs. Browser settings, installed custom skills, private project data, runtime configuration, native-host registration and unrelated user files stay in place. Bridge auto-start respects the previous preference.

The panel shows the registered installation folder. If you moved Multi-Script, run Setup from the folder you actually load first. Modified source files are protected from silent replacement. A staged update is not installed until Apply is used. Browser-store installs use their browser update service; an unknown install type cannot edit local files.

If the extension and registered folder report different versions, updating is blocked until Setup points to the correct loaded folder, or Reload completes an already installed update. An interrupted installation offers **Recover & reload**. Keep the complete folder and its `.updates` recovery data together. Recovery checks every required backup before changing installed files; a damaged backup leaves recovery pending with an error instead of partly restoring the installation. A transaction whose files already committed is verified and finalized. Bridge auto-start returns to its previous preference once installation/recovery settles, including after a browser-worker restart.

The updater checks free space and verifies each installed file before completing. Keep a backup for manual recovery and refresh provider tabs after reload. Browser settings live in the existing profile; private configuration, custom skills, studio data and unrelated files are excluded from managed replacement. Roblox/Figma/editor plugins installed into their host applications must still be updated separately from the bundled companion file. Unpacked extensions require explicit Apply/reload; the browser does not silently replace their source from a remote feed.

## Moving from the previous GitHub account

The official repository is now `krazydarky-code/Multi-Script`. Existing installs pinned to the previous account cannot discover this URL from an inaccessible old feed. Merge the complete current Dev package into the same permanent installation once, preserving private configuration and `runtime/studio-data`, run Setup, reload the extension and refresh provider tabs. Updating extension files alone does not change the native updater feed. The existing public signing key and extension identity are retained; no user GitHub login or new trust key is required.

## Publishing: automated for this repository

The repository is **krazydarky-code/Multi-Script**. The public update feed is:

`https://github.com/krazydarky-code/Multi-Script/releases/latest/download/dev-update.json`

The public signing key is pinned in `runtime/update-channel.json`. For cloud publishing, its private half is stored as the repository Actions secret `MS_UPDATE_SIGNING_KEY`; it is never committed, bundled or printed. A restricted local backup lives outside the source in the publisher’s home folder.

For each later update:

1. Make the changes and raise the release version consistently, including its release notes and QA report.
2. Open/merge the changes into `main`. **CI** runs the release gate and targeted integration/update checks. It rejects environment skips.
3. With repository variable `MS_AUTOPUBLISH=true`, successful main push CI triggers **Publish Dev release** for that exact tested commit. Automatic publishing is off when the variable is absent. Manual dispatch still validates main and CI. Planning skips already published versions before loading a signing key. Pull requests and fork workflows never receive the signing secret or publish.
4. The publisher downloads the checksum-pinned frozen Public companion, builds Dev and the bundle, signs the exact Dev archive, uploads every artifact to a draft, and verifies GitHub’s uploaded sizes/digests before publishing it as latest.
5. Open the release link, check the public feed and try an update on a separate older configured install before announcing it to users. Every bundle includes current `PUBLISHING.txt` and this guide.

Once the signing secret, frozen companion and explicit auto-publish variable are configured, no manual file upload, signing command or feed edit is needed for the normal flow. Rerunning CI for an already published version verifies its feed and leaves that release untouched. A real change requires a new version; the helper never overwrites a published release. An older workflow cannot move latest backwards or publish a commit that main has already moved past. Manual workflow dispatch still requires successful push CI for the exact current main commit.

`release-policy.json` pins the frozen Public hash and its source release. Keep that asset available; Public is never rebuilt from current Dev. The first migration release uses the checksum-pinned local frozen companion via `--public-archive`; that completed v6.49.9 release then hosts the companion for later automated versions. Public remains 6.42.0 and is not rebuilt.

## Private-key recovery and manual publisher fallback

Keep the restricted local private-key backup safe and do not commit it, attach it to a release or paste it into chat. The updater trust key is separate from the extension identity key. Do not casually regenerate either one: existing installs trust the public values they received.

If automation is unavailable, use the authenticated GitHub CLI and the existing backup key from an exact current main checkout:

```powershell
python tools/publish_github.py --repo krazydarky-code/Multi-Script --key "C:/Users/Claudiu/.multiscript-publisher/release.pem" --require-ci
```

This performs the same validated draft/build/sign/upload/publish flow. The publisher requires `cryptography` and GitHub CLI; ordinary users require neither. If the signing secret needs restoring, `gh secret set MS_UPDATE_SIGNING_KEY --repo krazydarky-code/Multi-Script` accepts the key via stdin. Never put its contents in command-line arguments.

## Recovery and coverage boundaries

The native updater verifies RSA/SHA-256 metadata, archive size/hash, Dev edition, monotonic version, extension identity, managed-file hashes and safe paths. It rejects new browser permissions, malformed archives, source edits and rollback versions. Corrupt staging files can be downloaded again. Downloading/checking never executes release code.

Apply requires the bridge to be stopped. A durable journal and backups allow ordinary write failures to roll back and interrupted applies to recover with Apply & reload. If backup corruption prevents recovery, retain `.updates` and restore a previous clean Dev ZIP while preserving private data. New browser permissions, external editor plugins, Python and third-party MCP dependencies need a manual update.

Local tests cover real signatures, actual TLS downloads, temporary-install upgrades, settings/private-file preservation, disk failures, killed-process recovery, helper guardrails and browser UI. The release QA report records remote CI/public-feed verification separately. Provider/account, physical-device and native-editor coverage remains explicitly bounded; no universal bug-free claim is made.

See [GitHub delivery safeguards](GITHUB_DELIVERY.md) for pacing, refusal handling and CI coverage. These safeguards do not override GitHub enforcement or guarantee an account cannot be suspended.

## Official references

- [GitHub release management](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)
- [GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets)
- [Chrome runtime updates](https://developer.chrome.com/docs/extensions/reference/api/runtime)
- [Chrome distribution limits](https://developer.chrome.com/docs/extensions/how-to/distribute/host-on-linux)
- [Install-type detection](https://developer.chrome.com/docs/extensions/reference/api/management)

## Automatic setup after a signed update (6.48.1)

The updater verifies the release signature, archive and installed managed files before running the fixed local installer. It runs the same launcher registration and framed self-test used by Setup.bat, without a batch window, bridge restart or pause prompt. A version-and-folder receipt prevents repeating successful setup.

A 6.48.0 client installs this patch using its older update flow. The newly loaded extension finishes setup when provider tabs are idle; refresh provider tabs if requested. Three actual automatic setup attempts are allowed per version; waiting for an active chat does not consume an attempt. If any attempt fails, the installed files remain intact, bridge startup stays paused, and **Help → Updates → Finish setup** retries safely. Details are in `logs/update-setup.log` and `logs/setup.log`. You can also run Setup.bat from the installed folder.

Extracting a separate downloaded folder does not change which unpacked extension your browser loads. Load that folder's `extension` directory and run its Setup.bat once. Updates shows both versions and the registered path if these differ. Private settings, engine preferences and custom skills are preserved during in-place updates. A browser-managed store extension follows its store's update mechanism.
