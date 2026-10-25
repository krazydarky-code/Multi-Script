# Multi-Script 4.5.0 — Opus 5.5 Release Candidate

A future-ready **Claude Opus 5.5** Notion Auto profile is now included. Anthropic released the model on September 22, 2026, but Notion had not yet announced it when this build was validated. The profile can be selected now: each new chat receives one minimal routing request, uses the real model if Notion has enabled it, and otherwise remains on Standard Auto without imitating Opus 5.5.

The secure ElevenLabs setup remains included: run `python runtime/configure_elevenlabs.py`, enter the API key through the hidden prompt, restart the bridge, and test one generated sound.
