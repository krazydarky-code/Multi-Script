#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Double-click in Finder (or run `bash MacOS_Start.command` in Terminal). The real work is in Start.sh,
# which also runs on Linux.
# If macOS says the file "cannot be opened" / "unidentified developer": right-click it -> Open,
# or in Terminal run:  xattr -dr com.apple.quarantine /path/to/Multi-Script
# If it says "permission denied":  chmod +x /path/to/Multi-Script/*.command /path/to/Multi-Script/*.sh
DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)" || exit 1
cd "$DIR" || exit 1
xattr -dr com.apple.quarantine "$DIR" >/dev/null 2>&1 || true
chmod +x ./*.sh ./*.command ./runtime/*.sh >/dev/null 2>&1 || true
exec bash ./Start.sh "$@"
