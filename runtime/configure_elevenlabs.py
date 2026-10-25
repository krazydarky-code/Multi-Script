#!/usr/bin/env python3
"""One-time secure local setup for ElevenLabs audio generation."""
from pathlib import Path
from getpass import getpass
import os
HERE = Path(__file__).resolve().parent
path = HERE / ".env"
print("Multi-Script ElevenLabs setup")
print("The key stays in runtime/.env on this computer and is never placed in the browser extension.")
key = getpass("Paste your ElevenLabs API key (input hidden): ").strip()
if not key:
    raise SystemExit("No key entered; nothing changed.")
lines = []
if path.is_file():
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("ELEVENLABS_API_KEY=")]
lines.append(f"ELEVENLABS_API_KEY={key}")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
try:
    os.chmod(path, 0o600)
except OSError:
    pass
print("ElevenLabs configured. Restart the Multi-Script bridge.")
