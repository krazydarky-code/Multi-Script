# Multi-Script 6.45.1 release verification

The configured publisher update passed **11 targeted local suites** with no
environment skips: publisher repository/upload guards, actual signing CLI,
signature checks, TLS download bounds, temporary-install update/rollback/crash
recovery, preserved private data, deterministic Dev/frozen-Public packaging,
current product/assets, skill application, browser update UI and Ultra routing,
and the full manifest content-script load contract.

The preceding creative/provider overhaul has [30 passing targeted 6.45.0 suites](QA_6.45.0.md),
including all 16 provider fixtures, the theme matrix and 506 settings controls.
Those historical results are not counted as newly rerun for this publishing change.

Current GitHub CI runs 18 targeted suites after its syntax/release gate, using
installed test dependencies and a pinned Playwright version. A missing browser or
other environment skip fails this job. Remote run status and the exact executed
results are available in Actions; the publisher attaches
`CI-verification-results.json` to the release before publication.

The release job accepts only successful push CI from this repository’s main
branch (or manual dispatch from main with exact successful push CI). It checks out
the tested commit, rejects a moved main, receives the private key only on that
trusted path, and cleans it from runner temporary storage. Every action is pinned
to a reviewed revision. Pull requests/forks do not receive signing material.

Draft upload state, byte size and GitHub SHA-256 digests are verified before the
release becomes public. The Dev archive’s signed feed contains its actual size,
checksum, version and HTTPS release URL. Published releases are never overwritten
by the helper. Public 6.42.0 remains pinned to its unchanged original checksum.

The private publisher key is excluded from source, commits, logs and packages.
Only its public key and feed URL ship. Local tests do not establish that a public
feed is reachable; final public-feed/download/update verification is performed
after the workflow publishes and reported separately.

The first configured build needs a one-time manual installation. Normal later
updates preserve browser settings and private files in the existing registered
folder. New browser permissions and external editor plugins/dependencies still
require manual work. Live provider accounts, physical phones and native editor
art-quality claims remain outside these fixture tests.
