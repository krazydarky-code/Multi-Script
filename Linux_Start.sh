#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Linux launcher: run `bash Linux_Start.sh` (or double-click -> "Run in Terminal").
# The real work is in Start.sh, shared with macOS.
cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" || exit 1
exec bash ./Start.sh "$@"
