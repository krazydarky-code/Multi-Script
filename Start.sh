#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Runs the Multi-Script bridge in this terminal (macOS AND Linux; MacOS_Start.command calls it).
# You normally do not need it: after Setup.sh the terminal icon in the chat bar starts and stops
# the bridge. Use this when setup is not possible (Flatpak/Snap browsers, no native messaging),
# or to watch the console output. Press Ctrl+C or close the window to stop it.
#   bash Start.sh [--no-pause] [--yes]      (--yes: replace a running bridge without asking)
SRC="${BASH_SOURCE[0]:-$0}"
while [ -L "$SRC" ]; do
    LINK="$(readlink "$SRC")"
    case "$LINK" in /*) SRC="$LINK" ;; *) SRC="$(dirname "$SRC")/$LINK" ;; esac
done
MS_ROOT="$(cd "$(dirname "$SRC")" 2>/dev/null && pwd)" || exit 1
cd "$MS_ROOT" || exit 1
MS_LOG="start.log"
mkdir -p logs 2>/dev/null
echo "===== $(date)  Start.sh =====" >> logs/start.log 2>/dev/null

if [ ! -f runtime/bridge.py ] || [ ! -f runtime/unix_env.sh ]; then
    echo "ERROR: runtime/bridge.py not found. Extract the WHOLE download, then run this again."
    [ -t 0 ] && read -n 1 -s -r -p "Press any key to close..." && echo
    exit 1
fi
# shellcheck disable=SC1091
. runtime/unix_env.sh
YES=0
for a in "$@"; do
    case "$a" in --no-pause) MS_NO_PAUSE=1 ;; --yes|-y) YES=1 ;; esac
done

ms_check_location || { ms_pause; exit 1; }
ms_clear_quarantine
if ! ms_find_python; then ms_say ""; ms_python_hint; ms_pause; exit 1; fi
ms_ensure_websockets || { ms_pause; exit 1; }

"$PY" runtime/bridge_status.py --quiet
case $? in
    0)
        ms_say "A Multi-Script bridge of this version is already running (port $MS_PORT)."
        if [ "$YES" = "1" ]; then ANS=y
        elif [ -t 0 ]; then read -r -t 12 -p "Restart it with this window? [y/N] " ANS; echo
        else ANS=n; fi
        case "$ANS" in y|Y) ms_say "Restarting...";; *) exit 0;; esac
        ;;
    2)
        ms_say "An OLDER Multi-Script bridge (previous download/folder) holds port $MS_PORT - replacing it with this folder's."
        ;;
    3)
        ms_say "Port $MS_PORT is used by a program that is not a Multi-Script bridge."
        ms_say "Close it, or run:  ZS_BRIDGE_PORT=17614 bash Start.sh"
        ms_pause
        exit 1
        ;;
esac

export PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 ZS_STARTED_BY=Start.sh
"$PY" -u runtime/bridge.py
RC=$?
ms_say ""
ms_say "The bridge stopped (exit code $RC)."
ms_pause
exit $RC
