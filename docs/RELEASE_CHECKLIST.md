# Release checklist

## Code and QA
- [ ] Set bridge, extension, adapter, changelog, and release-manifest versions
- [ ] Run `python tools/release_check.py`
- [ ] Run parser, provider, bridge, MCP, launcher, and browser fixture tests
- [ ] Confirm the provider count agrees everywhere: `runtime/product-manifest.json`,
      `tests/test_cross_provider_tool_matrix.js`, `tests/test_provider_benchmarks.js`
      and the five registration points in `docs/ARCHITECTURE.md`
- [ ] Confirm no generated files, logs, secrets, or credentials are packaged
- [ ] Test a clean install from the ZIP on Windows and one Chromium browser
- [ ] Test on macOS and Linux (CI now runs both; a local pass is still worth it for the
      engine launchers, which CI does not have the engines to exercise)

## Product
- [ ] Verify bridge offline/online, editor attached/detached, and recovery states
- [ ] Verify `GET /diagnostics` answers and `bridge_status.py --json` prints it
- [ ] Verify provider settings persist independently
- [ ] Verify Notion routing request is sent once in a new chat
- [ ] Verify Fast mode disables optional loops
- [ ] Verify Canvas/Figma fallback and direct-engine routing

## Distribution
- [ ] Review INSTALL, PRIVACY, SECURITY, SUPPORT, LICENSE, and third-party notices
- [ ] Build the current Dev ZIP and combined Bundle using `tools/build_release.py`
- [ ] Confirm Dev is newer than the checksum-pinned frozen Public companion;
      preserve Public bytes and version unchanged (see `RELEASE_POLICY.md`)
- [ ] Check both inner archives against the bundle manifest and SHA-256 sums
- [ ] Publish SHA-256 checksums
- [ ] Upload screenshots, store description, privacy disclosure, and release notes
- [ ] Tag the version only after smoke testing the exact uploaded archives
