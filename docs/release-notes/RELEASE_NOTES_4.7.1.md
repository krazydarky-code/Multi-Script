# Multi-Script 4.7.1 — JSON Tool Protocol Fix

Every provider now gets exactly one tool-call format: one plain-text, unfenced JSON object using `command` and `params`. The extension also normalizes accidental provider-native invoke markup internally, so Arena and other sites execute the intended Roblox call and display the normal tool chip instead of entering a format-error loop.
