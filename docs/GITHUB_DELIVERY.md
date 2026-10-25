# GitHub delivery and request safeguards

Official source and releases: https://github.com/krazydarky-code/Multi-Script

## Maintainer setup

The public feed in `runtime/update-channel.json`, product metadata and active download links use the same repository. The existing RSA public key and browser extension identity are preserved. Keep the private signing key outside source/releases; GitHub Actions uses the encrypted repository secret `MS_UPDATE_SIGNING_KEY`. Set repository variable `MS_AUTOPUBLISH=true` only after the first verified release/bootstrap. Leave it absent/false to use manual publishing. Never paste private keys or tokens into issues, chats, release notes or command-line arguments.

The first release can be published from the exact tested main commit using the existing local key and `--public-archive` pointing to the unchanged Public 6.42.0 ZIP. `release-policy.json` pins its hash and the first migration release as its future source. Later releases require a consistent higher numeric version; the publisher never replaces an already published version.

## Normal automation

CI uses four bounded Linux shards while preserving the prior targeted checks. Native ProseMirror dependencies are installed for the real ChatGPT editor tests. A collector rejects missing, duplicate, failed or skipped required results before emitting the single release receipt. The separate real Blender Windows job remains. A successful workflow_run must be a same-repository main push; pull requests and fork events cannot publish or access signing material. The publisher rechecks main before draft changes and again before publication.

`--check-only --require-ci` reads state without loading a signing key or changing GitHub. Already published versions are verified and skipped. The normal path builds and signs the exact archive, uploads assets serially, reuses matching draft assets, verifies uploaded size/digest/state, and publishes the verified draft as latest. GitHub mutations are spaced at least one second apart. There is no automatic retry/replay of failed publication writes, no polling release scheduler, no per-file API commit loop, and no force push.

## Updater request handling

Daily successful checks remain the default. Network failures use persistent exponential browser backoff, starting at 15 minutes and capped at one day. A 429 or rate-limited 403 ends the current request immediately and persists the Retry-After/reset deadline in `.updates/host-retry.json`. Manual Check cannot bypass that server cooldown. Authentication/access/missing-host refusals pause checks for 24 hours. A deliberately changed configured feed gets its own cooldown scope, so the inaccessible old host cannot block a corrected migration.

This reduces avoidable request traffic. It cannot establish why an earlier account was suspended or guarantee that GitHub will never restrict an account. Do not rotate accounts/tokens/IPs to bypass enforcement. Use GitHub support for account restrictions and honor provider instructions.

## Existing installations

An old pinned feed cannot discover a new owner when the old repository is inaccessible. A one-time full Dev merge into the same permanent installation updates the feed; keep private configuration, custom skills, browser storage and native project data. Run Setup from that folder, reload the extension and refresh provider tabs. The numeric product version stays 6.49.9 for this migration, so existing 6.49.9 builds need this bootstrap manually; subsequent higher versions use the normal signed updater.

## References

- https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
