# Dev-first release policy

Dev is the primary edition and the only rolling build. All features, fixes and
verification apply to Dev. Public 6.42.0 is a frozen compatibility companion.
It is older and does not receive current features or fixes. Do not regenerate it
from the development source or change its version label to imply it is current.

`release-policy.json` pins the Public filename, version and SHA-256. Packaging
requires Dev's actual manifest version to be newer than Public. It verifies the
old archive's checksum, edition, CRC and stable extension identity. A changed or
missing companion stops packaging with an explicit error. An existing different
Public archive is never overwritten.

Build from the source directory:

```sh
python tools/release_check.py
python tools/build_release.py --output release --public-archive /path/to/Multi-Script-6.42.0-Public.zip
```

If the frozen Public ZIP is already in the output folder, `--public-archive` can
be omitted. The original archive remains separate from the source tree.

The outputs are the current Dev ZIP, the unchanged Public ZIP, a combined Bundle
ZIP containing both, a release manifest and SHA-256 checksums. `START-HERE.txt`
inside the bundle tells users to install Dev. Each inner ZIP contains a complete
extension, local bridge and source. Install one edition at a time; keep its
extension and runtime together. Changing the Public baseline requires an explicit
release-policy update, a separately reviewed Public release and a newer Dev.

Packaging excludes private workspace data, logs, tokens, local native-host paths
and generated files, and substitutes the example MCP configuration. Source
edition flags remain Dev with no product caps. Public retains its original limits.

Verify packaging with `python tests/test_dev_release_policy.py`. Verify changed
features separately using `python tools/verify.py` and record actual results in
the release QA report. Passing package checks does not certify live providers.
