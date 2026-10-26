#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# One-time setup for macOS AND Linux (MacOS_Setup.command just calls this file).
#
#   bash Setup.sh                  register the launcher with your browser, start + verify the bridge
#   bash Setup.sh --no-start       register only
#   bash Setup.sh --keep-running   leave an already-running bridge of the same version alone
#   bash Setup.sh --uninstall      remove the browser registration (and the Linux menu entry)
#   bash Setup.sh --extension-id <id>   add an extra extension id
#   bash Setup.sh --no-pause       do not wait for a key at the end
#
# Safe to re-run; re-run it after EVERY update (new download / new folder). A transcript
# is written to logs/setup.log.
SRC="${BASH_SOURCE[0]:-$0}"
while [ -L "$SRC" ]; do
    LINK="$(readlink "$SRC")"
    case "$LINK" in /*) SRC="$LINK" ;; *) SRC="$(dirname "$SRC")/$LINK" ;; esac
done
MS_ROOT="$(cd "$(dirname "$SRC")" 2>/dev/null && pwd)" || exit 1
cd "$MS_ROOT" || exit 1
MS_LOG="setup.log"
mkdir -p logs 2>/dev/null
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8

if [ ! -f runtime/unix_env.sh ] || [ ! -f runtime/install_native_host.py ]; then
    echo
    echo "  ERROR: runtime/ files not found. Extract the WHOLE download, then run this again."
    [ -t 0 ] && read -n 1 -s -r -p "Press any key to close..." && echo
    exit 1
fi
# shellcheck disable=SC1091
. runtime/unix_env.sh

ARGS=""; DESKTOP=1; UNINSTALL=0; NO_START=0
for a in "$@"; do
    case "$a" in
        --no-pause) MS_NO_PAUSE=1 ;;
        --no-desktop-entry) DESKTOP=0 ;;
        --uninstall) UNINSTALL=1; ARGS="$ARGS $a" ;;
        --no-start) NO_START=1; ARGS="$ARGS $a" ;;
        *) ARGS="$ARGS $a" ;;
    esac
done
ms_say ""
ms_say "  Multi-Script setup ($MS_OS) - folder: $MS_ROOT"
echo "===== $(date)  Setup.sh $* =====" >> "logs/$MS_LOG" 2>/dev/null

ms_check_location || { ms_pause; exit 1; }
ms_clear_quarantine
ms_make_executable

DESKTOP_FILE="${XDG_DATA_HOME:-$HOME/.local/share}/applications/multi-script-bridge.desktop"
if [ "$UNINSTALL" = "1" ]; then rm -f "$DESKTOP_FILE" 2>/dev/null; fi

if ! ms_find_python; then
    ms_say ""
    ms_python_hint
    ms_pause
    exit 1
fi
ms_say "  ok Python: $PY"
if [ "$UNINSTALL" != "1" ]; then
    ms_ensure_websockets || { ms_pause; exit 1; }
fi

# shellcheck disable=SC2086
"$PY" runtime/install_native_host.py --no-pause $ARGS
RC=$?
if [ "$RC" = "0" ] && [ "$UNINSTALL" != "1" ]; then
    # 6.28: best-effort engine prerequisites (uv for Unity/Blender, the BlenderMCP
    # add-on download, and the bundled Blender entry in config.json). Never fails setup.
    "$PY" runtime/setup_engines.py || true
fi
ms_say ""
if [ "$RC" = "0" ] && [ "$UNINSTALL" != "1" ]; then
    # Linux: an application-menu entry that runs the bridge in a terminal (no browser integration needed).
    if [ "$MS_OS" = "Linux" ] && [ "$DESKTOP" = "1" ]; then
        if mkdir -p "$(dirname "$DESKTOP_FILE")" 2>/dev/null; then
            ESC_ROOT="$(printf '%s' "$MS_ROOT" | sed 's/%/%%/g')"
            {
                echo "[Desktop Entry]"
                echo "Type=Application"
                echo "Name=Multi-Script Bridge"
                echo "Comment=Run the Multi-Script bridge in a terminal"
                echo "Exec=bash \"$ESC_ROOT/Start.sh\""
                echo "Path=$MS_ROOT"
                echo "Terminal=true"
                echo "Categories=Development;"
            } > "$DESKTOP_FILE" 2>/dev/null && ms_say "  ok added \"Multi-Script Bridge\" to your application menu"
        fi
    fi
    if [ "$NO_START" != "1" ]; then
        ms_say "  Final check:"
        "$PY" runtime/bridge_status.py
    fi
    ms_say "  Now fully restart the browser (close ALL its windows), reload the Multi-Script extension in"
    ms_say "  chrome://extensions (or edge://extensions / brave://extensions) and refresh your AI chat tab."
elif [ "$RC" != "0" ]; then
    ms_say "  Setup did not finish (code $RC). Read the message above."
    ms_say "  A transcript was saved to: $MS_ROOT/logs/setup.log"
    ms_say "  You can still run the bridge directly:  bash Start.sh"
fi
ms_pause
exit $RC
