# Multi-Script 6.32.2 — enhanced prompts not sending

The failure was reproduced in real Chromium with the full SuperApp extension chain: the review accepted an improved prompt, but a stale `A.stop` from a previous Stop made `submitAndGetBase` attempt zero sends. There was no error because the send loop considered itself stopped.

The accepted new send now clears that old flag before submitting. A newer Stop or conversation change during review still cancels the send. Improved, edited, original and automatic sends each produce one message; Cancel leaves the original draft untouched.

## Update

Extract `Multi-Script-6.32.2-Full.zip`, preserve your runtime configuration/custom settings, and update the installed extension files. Reload the extension in Chrome/Edge's extensions page and reload the AI provider tab. Existing tabs continue running old JavaScript until reloaded.

This release also includes the previous creative-tool hotfix. If upgrading from 6.32.0 or older, update the runtime files and restart the bridge too. The supplied extension identity is preserved in the Full bundle. Use a fresh chat or refresh the existing tool catalogue after a bridge update.

## Passed verification

- Eight full-chain Chromium scenarios: fresh enhanced send; enhanced, original, edited and automatic sends after Stop; Cancel; Stop during review; conversation navigation during review. Each successful scenario checks exactly one native send containing the chosen text, and all scenarios check no page errors.
- Twelve send-gate regression cases and thirteen prompt-enhancer sections pass.
- Existing enhancer presentation and effort wiring checks pass across all twelve provider app blocks.
- All twelve content-script chains load without errors.
- All seven creative-tool hotfix tests still pass through production bridge dispatch, including actual SVG and local WAV creation.
- Release gate checks manifest references, version metadata, 897 skills and 115 JavaScript files.

Tests use local provider fixtures; live authenticated provider accounts were not used. The IDE executable is not rebuilt by this extension hotfix.
