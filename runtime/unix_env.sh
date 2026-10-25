# SPDX-License-Identifier: GPL-3.0-or-later
# Shared helpers for Setup.sh / Start.sh (macOS and Linux). Sourced, never run directly.
# Written for bash 3.2 (the bash that ships with macOS): keep it to plain POSIX-style
# constructs - nothing newer than bash 3.2 offers.

MS_PORT="${ZS_BRIDGE_PORT:-17613}"
MS_OS="$(uname -s 2>/dev/null || echo Unknown)"
PY=""

ms_say() {
    printf '%s\n' "$*"
    if [ -n "$MS_ROOT" ] && [ -d "$MS_ROOT/logs" ]; then printf '%s\n' "$*" >> "$MS_ROOT/logs/$MS_LOG" 2>/dev/null; fi
}

# Wait for a key only when a person is looking at this window.
ms_pause() {
    [ "$MS_NO_PAUSE" = "1" ] && return 0
    [ -t 0 ] && [ -t 1 ] || return 0
    printf '\n'
    read -n 1 -s -r -p "Press any key to close this window..." </dev/tty 2>/dev/null || true
    printf '\n'
}

ms_die() {
    ms_say ""
    ms_say "  ERROR: $*"
    ms_pause
    exit 1
}

# Echo how to install Python 3.9+ on this machine.
ms_python_hint() {
    ms_say "  Python 3.9 or newer is required."
    if [ "$MS_OS" = "Darwin" ]; then
        ms_say "    - With Homebrew:   brew install python"
        ms_say "    - Or download it:  https://www.python.org/downloads/macos/"
        ms_say "    - (Apple's own /usr/bin/python3 only works after:  xcode-select --install )"
        return
    fi
    id_like=""
    if [ -r /etc/os-release ]; then id_like="$(. /etc/os-release 2>/dev/null; echo "$ID $ID_LIKE")"; fi
    case " $id_like " in
        *debian*|*ubuntu*|*mint*|*pop*) ms_say "    sudo apt update && sudo apt install -y python3 python3-venv python3-pip" ;;
        *fedora*|*rhel*|*centos*|*rocky*|*alma*) ms_say "    sudo dnf install -y python3 python3-pip" ;;
        *arch*|*manjaro*|*endeavour*) ms_say "    sudo pacman -S --needed python python-pip" ;;
        *suse*) ms_say "    sudo zypper install python3 python3-pip" ;;
        *alpine*) ms_say "    sudo apk add python3 py3-pip" ;;
        *) ms_say "    Install python3 (3.9+) and pip with your package manager, or from https://www.python.org/downloads/" ;;
    esac
}

ms_py_ok() {
    # $1 = interpreter. True when it runs and is Python >= 3.9.
    [ -n "$1" ] || return 1
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1
}

# Sets PY. Prefers this folder's private venv (created by Setup.sh when the system
# Python refuses pip installs), then Homebrew / python.org / distro interpreters.
ms_find_python() {
    PY=""
    if [ -x "$MS_ROOT/.venv/bin/python" ] && ms_py_ok "$MS_ROOT/.venv/bin/python"; then
        PY="$MS_ROOT/.venv/bin/python"; return 0
    fi
    cands=""
    if [ "$MS_OS" = "Darwin" ]; then
        for d in /opt/homebrew/bin /usr/local/bin /Library/Frameworks/Python.framework/Versions/Current/bin; do
            for n in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
                [ -x "$d/$n" ] && cands="$cands $d/$n"
            done
        done
    fi
    for n in python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
        p="$(command -v "$n" 2>/dev/null)"
        [ -n "$p" ] && cands="$cands $p"
    done
    for c in $cands; do
        # On a Mac without the Command Line Tools /usr/bin/python3 is a stub that pops up
        # an installer dialog instead of running. Never call it in that state.
        if [ "$MS_OS" = "Darwin" ] && [ "$c" = "/usr/bin/python3" ] && ! xcode-select -p >/dev/null 2>&1; then
            continue
        fi
        if ms_py_ok "$c"; then PY="$c"; return 0; fi
    done
    return 1
}

ms_have_ws() { "$PY" -c 'import websockets; from PIL import ImageGrab' >/dev/null 2>&1; }

# Makes `import websockets` work, whatever the distro's pip policy:
#   1. already installed            2. pip install --user
#   3. a private .venv in this folder (PEP 668 "externally-managed" systems, e.g. Debian 12 / Ubuntu 24.04)
#   4. pip --break-system-packages (last resort)
ms_ensure_websockets() {
    ms_have_ws && return 0
    ms_say "  .. installing the one dependency (websockets) - first run only..."
    tmp="$(mktemp 2>/dev/null || echo /tmp/ms_pip.$$)"
    if "$PY" -m pip install --user websockets Pillow >"$tmp" 2>&1 && ms_have_ws; then rm -f "$tmp"; return 0; fi
    if "$PY" -m venv "$MS_ROOT/.venv" >>"$tmp" 2>&1 && "$MS_ROOT/.venv/bin/python" -m pip install websockets Pillow >>"$tmp" 2>&1; then
        PY="$MS_ROOT/.venv/bin/python"
        if ms_have_ws; then
            ms_say "  ok installed into a private environment: $MS_ROOT/.venv (your system Python was left alone)"
            rm -f "$tmp"; return 0
        fi
    fi
    rm -rf "$MS_ROOT/.venv" 2>/dev/null
    if "$PY" -m pip install --user --break-system-packages websockets Pillow >>"$tmp" 2>&1 && ms_have_ws; then rm -f "$tmp"; return 0; fi
    ms_say "  Could not install websockets. Last messages from pip:"
    tail -n 6 "$tmp" 2>/dev/null | sed 's/^/    /'
    rm -f "$tmp"
    if [ "$MS_OS" != "Darwin" ]; then
        ms_say "  On Debian/Ubuntu you may need:  sudo apt install python3-venv python3-pip   (or: sudo apt install python3-websockets)"
    fi
    ms_say "  Then run this script again. (Manual install:  $PY -m pip install websockets Pillow )"
    return 1
}

# Refuse to run from places that disappear or are read-only (zip preview, temp
# folders, macOS "App Translocation" of a quarantined download).
ms_check_location() {
    case "$MS_ROOT" in
        */AppTranslocation/*|/private/var/folders/*|/var/folders/*|/tmp/*|/var/tmp/*|*.zip/*)
            ms_say ""
            ms_say "  This looks like a temporary / zipped location:"
            ms_say "    $MS_ROOT"
            ms_say "  Extract the WHOLE download to a normal folder (e.g. ~/Documents or ~/Multi-Script) and run this there,"
            ms_say "  otherwise the browser registration breaks as soon as the temporary folder is cleaned."
            if [ "$MS_OS" = "Darwin" ]; then
                ms_say "  (macOS runs files from a quarantined download in a read-only copy; moving the folder fixes that.)"
            fi
            [ "$ZS_ALLOW_TEMP_FOLDER" = "1" ] && return 0
            return 1 ;;
    esac
    return 0
}

# macOS only: files from a browser download carry a quarantine flag that makes
# Gatekeeper re-ask for every script. This is the user's own folder, so clear it.
ms_clear_quarantine() {
    [ "$MS_OS" = "Darwin" ] || return 0
    command -v xattr >/dev/null 2>&1 || return 0
    xattr -dr com.apple.quarantine "$MS_ROOT" >/dev/null 2>&1 || true
}

ms_make_executable() {
    chmod +x "$MS_ROOT"/Setup.sh "$MS_ROOT"/Start.sh "$MS_ROOT"/MacOS_Setup.command "$MS_ROOT"/MacOS_Start.command \
        "$MS_ROOT"/Linux_Setup.sh "$MS_ROOT"/Linux_Start.sh \
        "$MS_ROOT"/runtime/native_host.py "$MS_ROOT"/runtime/native_host.sh >/dev/null 2>&1 || true
}
