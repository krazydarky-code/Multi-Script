# Multi-Script 4.4.0 — Direct ElevenLabs Audio

Sound-effect, ambience, Foley, UI-audio, loop, and musical-element requests can now call ElevenLabs directly through the local bridge. The resulting MP3 or eligible PCM asset is saved under `runtime/generated/audio`, recorded with metadata and checksum, then imported and configured through the target engine MCP. The user does not open ElevenLabs for each request.

One-time setup: run `python runtime/configure_elevenlabs.py`, enter the API key in the hidden terminal prompt, and restart the bridge. The secret stays local. ElevenLabs plan, quota, and licensing terms still apply.
