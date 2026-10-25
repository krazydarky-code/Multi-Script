# SPDX-License-Identifier: GPL-3.0-or-later
# media_relay.py
# ──────────────────────────────────────────────────────────────────────────
#  Multi-Script Media Relay - let a user hand a photo or a video to a chat
#  site that has no file-upload control (or whose upload is disabled).
#
#  ── The real problem ───────────────────────────────────────────────────
#
#  Several of the AI chat surfaces Multi-Script drives expose NO file input
#  at all: the composer is a plain contenteditable with a send button and
#  nothing else. Others have an upload button that is hidden, disabled, or
#  refuses video. A user with a screenshot of a broken HUD or a 20-second
#  clip of a physics glitch simply cannot show the model the thing they are
#  asking about - so they describe it in prose and the model guesses.
#
#  ── How the relay works ────────────────────────────────────────────────
#
#  The relay deliberately does NOT try to synthesise a fake <input type=file>
#  and forge a File object into a framework's upload pipeline. That approach
#  breaks on every site that reconciles its own DOM (React/Vue/Svelte), and
#  when it does work it leaks the file to a third-party CDN in a way the user
#  did not ask for.
#
#  Instead it uses the one channel every contenteditable already speaks:
#  the CLIPBOARD. Browsers accept a real paste of an image into a rich-text
#  editor as a first-class attachment, with no upload widget involved - and
#  for a site that refuses video, the relay writes a small, bounded set of
#  extracted FRAMES plus a text manifest, which is enough for a model to
#  reason about motion without shipping a 40 MB file.
#
#  This module is the STAGING + CONVERSION half (pure Python, no browser):
#
#    1. stage()      - accept raw bytes, sniff the real type from the magic
#                      number (never trust the client's claimed MIME), enforce
#                      size/type policy, and write to the relay spool.
#    2. prepare()    - turn a staged item into one or more PASTE PAYLOADS:
#                        - image/*  -> a single image payload
#                        - video/*  -> N frame payloads + a text manifest,
#                                      using ffmpeg when it is available and a
#                                      honest "frames unavailable" manifest
#                                      when it is not.
#    3. manifest()   - a plain-text description the model can read, so even
#                      when no frame could be extracted the loop still knows
#                      what the user attached and can ask a sharp question.
#    4. release()    - drop spooled bytes (always called after a send, or on
#                      demand), so nothing accumulates on disk.
#
#  ── Safety rules (all enforced here, not in the caller) ────────────────
#
#   * Loopback only. This module never opens a socket; bridge.py does, on
#     127.0.0.1, and this module refuses any path that could escape the spool.
#   * Type allow-list by magic number. A ".png" that is actually an EXE is
#     rejected before a byte reaches the spool.
#   * Hard size ceiling per item and per spool, so a hostile/looping client
#     cannot fill the disk.
#   * Path traversal is impossible: item ids are generated here (never taken
#     from the client) and every join is re-checked to stay inside the spool.
#   * Everything is ephemeral: a released item is unlinked, and stale items
#     older than MAX_AGE_SECONDS are swept on every stage().
# ──────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

# ── Policy ────────────────────────────────────────────────────────────────
# A relay payload travels base64 over a loopback HTTP request and is held in
# memory by the browser before it becomes a paste. The ceilings below are
# chosen so that the WORST case is still a request the browser comfortably
# handles, and so a single accidental drop of a 4 GB video is refused with a
# readable message rather than hanging the bridge.

MAX_ITEM_BYTES = 24 * 1024 * 1024        # 24 MB per staged item
MAX_SPOOL_BYTES = 96 * 1024 * 1024       # 96 MB across the whole spool
MAX_AGE_SECONDS = 30 * 60                # staged items are swept after 30 min
MAX_FRAMES = 6                           # video -> frame payloads
MAX_ITEM_COUNT = 12                      # distinct items kept at once

# Magic-number allow-list. Extension and client MIME are advisory only; the
# bytes decide. Each entry: (label, mime, kind, test).
def _png(b):
    return b[:8] == b"\x89PNG\r\n\x1a\n"


def _jpeg(b):
    return b[:3] == b"\xff\xd8\xff"


def _gif(b):
    return b[:6] in (b"GIF87a", b"GIF89a")


def _webp(b):
    return b[:4] == b"RIFF" and b[8:12] == b"WEBP"


def _bmp(b):
    return b[:2] == b"BM"


def _mp4(b):
    # ISO-BMFF: a box size then 'ftyp' at offset 4.
    return len(b) >= 12 and b[4:8] == b"ftyp"


def _webm(b):
    return b[:4] == b"\x1a\x45\xdf\xa3"


def _avi(b):
    return b[:4] == b"RIFF" and b[8:12] == b"AVI "


def _mov(b):
    return len(b) >= 12 and b[4:8] in (b"moov", b"mdat", b"ftyp", b"wide", b"free")


IMAGE_TYPES = [
    ("png", "image/png", "image", _png),
    ("jpeg", "image/jpeg", "image", _jpeg),
    ("gif", "image/gif", "image", _gif),
    ("webp", "image/webp", "image", _webp),
    ("bmp", "image/bmp", "image", _bmp),
]
VIDEO_TYPES = [
    ("mp4", "video/mp4", "video", _mp4),
    ("webm", "video/webm", "video", _webm),
    ("avi", "video/x-msvideo", "video", _avi),
]
# Container sniffing for MOV is loose (moov/mdat also appear mid-file), so it
# is only consulted when nothing firmer matched, and only on the header.
MOV_TYPE = ("mov", "video/quicktime", "video", _mov)

ALL_TYPES = IMAGE_TYPES + VIDEO_TYPES


def sniff(data: bytes):
    """Identify real type from the magic number. Returns (ext, mime, kind) or
    (None, 'application/octet-stream', 'unknown'). Never raises."""
    if not data:
        return (None, "application/octet-stream", "unknown")
    head = data[:32]
    for ext, mime, kind, test in ALL_TYPES:
        try:
            if test(head):
                return (ext, mime, kind)
        except Exception:
            continue
    ext, mime, kind, test = MOV_TYPE
    try:
        if test(head):
            return (ext, mime, kind)
    except Exception:
        pass
    return (None, "application/octet-stream", "unknown")


# ── Spool ─────────────────────────────────────────────────────────────────


def _spool_dir():
    """Where staged items live. Sibling of bridge.py's logs/, so it travels
    with the install and is trivially clearable. Created on first use."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "generated", "media-relay")
    os.makedirs(path, exist_ok=True)
    return path


class RelayError(Exception):
    """A refusal the user can act on (too big, wrong type, unknown id)."""


class MediaRelay:
    """Stage / prepare / release. Thread-safe: bridge.py serves requests from
    several asyncio tasks and, for the companion port, from its own loop."""

    def __init__(self, spool=None):
        self._lock = threading.Lock()
        self._spool = spool or _spool_dir()
        self._items = {}  # id -> {ext, mime, kind, name, bytes, path, created}

    # ── lifecycle ────────────────────────────────────────────────────────
    def _sweep_locked(self):
        """Drop items that are too old or push the spool past its ceiling.
        Called with self._lock held. Best-effort: a file that will not unlink
        is forgotten rather than retried forever."""
        now = time.time()
        stale = [i for i, it in self._items.items() if now - it["created"] > MAX_AGE_SECONDS]
        for i in stale:
            self._unlink_locked(i)
        # Ceiling: evict oldest first, then count cap.
        total = sum(it["bytes"] for it in self._items.values())
        if total > MAX_SPOOL_BYTES:
            for i in sorted(self._items, key=lambda k: self._items[k]["created"]):
                if total <= MAX_SPOOL_BYTES:
                    break
                total -= self._items[i]["bytes"]
                self._unlink_locked(i)
        if len(self._items) > MAX_ITEM_COUNT:
            for i in sorted(self._items, key=lambda k: self._items[k]["created"]):
                if len(self._items) <= MAX_ITEM_COUNT:
                    break
                self._unlink_locked(i)

    def _unlink_locked(self, item_id):
        it = self._items.pop(item_id, None)
        if not it:
            return
        path = it.get("path")
        # Re-check containment before unlinking: never trust a stored path.
        try:
            if path and os.path.abspath(path).startswith(os.path.abspath(self._spool) + os.sep):
                os.unlink(path)
        except Exception:
            pass

    # ── stage ────────────────────────────────────────────────────────────
    def stage(self, data: bytes, claimed_name: str = "", claimed_mime: str = "") -> dict:
        """Accept raw bytes. Returns the staged item's public descriptor.

        Refuses: empty, over MAX_ITEM_BYTES, or a type not on the allow-list.
        The claimed name/MIME are used only for the (bounded, sanitised)
        display name and are never trusted for the type decision.
        """
        if not isinstance(data, (bytes, bytearray)):
            raise RelayError("media payload must be raw bytes")
        data = bytes(data)
        if not data:
            raise RelayError("the file is empty")
        if len(data) > MAX_ITEM_BYTES:
            raise RelayError(
                "the file is %.1f MB; the relay accepts up to %d MB per file"
                % (len(data) / 1048576.0, MAX_ITEM_BYTES // 1048576)
            )

        ext, mime, kind = sniff(data)
        if kind == "unknown":
            raise RelayError(
                "that file is not a supported photo or video "
                "(accepted: png, jpeg, gif, webp, bmp, mp4, webm, avi, mov)"
            )

        item_id = uuid.uuid4().hex[:16]
        safe_name = _safe_display_name(claimed_name, ext)
        path = os.path.join(self._spool, item_id + "." + ext)
        with self._lock:
            self._sweep_locked()
            # Containment assertion: the id is ours, but assert anyway - a
            # future edit must not be able to write outside the spool.
            if not os.path.abspath(path).startswith(os.path.abspath(self._spool) + os.sep):
                raise RelayError("internal: refused to write outside the relay spool")
            with open(path, "wb") as fh:
                fh.write(data)
            rec = {
                "id": item_id,
                "ext": ext,
                "mime": mime,
                "kind": kind,
                "name": safe_name,
                "bytes": len(data),
                "path": path,
                "created": time.time(),
                "claimedMime": str(claimed_mime or "")[:80],
            }
            self._items[item_id] = rec
        return self._public(rec)

    # ── prepare ──────────────────────────────────────────────────────────
    def prepare(self, item_id: str) -> dict:
        """Turn a staged item into paste payloads.

        An image yields one image payload. A video yields up to MAX_FRAMES
        frame payloads extracted with ffmpeg, plus a manifest. When ffmpeg is
        unavailable the call still SUCCEEDS and returns the manifest alone,
        because a relay that refuses to say anything is worse than one that
        says "I have your clip, here is its duration, I could not extract
        frames" - the model can then ask a precise question.
        """
        with self._lock:
            self._sweep_locked()
            rec = self._items.get(item_id)
            if not rec:
                raise RelayError("that attachment has expired; re-drop it")
            snapshot = dict(rec)
        with open(snapshot["path"], "rb") as fh:
            data = fh.read()

        payloads = []
        if snapshot["kind"] == "image":
            payloads.append({
                "kind": "image",
                "mime": snapshot["mime"],
                "name": snapshot["name"],
                "dataUrl": _data_url(snapshot["mime"], data),
            })
            note = "one image is ready to paste into the composer"
        else:
            frames, frame_note = self._extract_frames(snapshot)
            payloads.extend(frames)
            duration = _probe_duration(snapshot["path"])
            note = frame_note

        manifest = self.manifest(snapshot, payloads, note)
        return {
            "id": item_id,
            "kind": snapshot["kind"],
            "mime": snapshot["mime"],
            "name": snapshot["name"],
            "bytes": snapshot["bytes"],
            "payloads": payloads,
            "manifest": manifest,
            "note": note,
        }

    def _extract_frames(self, rec):
        """Best-effort frame extraction. Returns (payloads, note)."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return [], ("no frames were extracted because ffmpeg is not installed; "
                        "the manifest below still describes the clip")
        tmp = tempfile.mkdtemp(prefix="zs-relay-")
        try:
            pattern = os.path.join(tmp, "f%02d.jpg")
            # -vf fps + scale: a handful of evenly spaced, modestly sized frames
            # is what a model can actually reason about (and what a composer
            # will accept). Strip audio: a frame paste has no audio channel.
            cmd = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-i", rec["path"],
                "-vf", "fps=1/2,scale='min(720,iw)':-2",
                "-frames:v", str(MAX_FRAMES),
                "-q:v", "4", "-an", pattern,
            ]
            proc = subprocess.run(cmd, capture_output=True, timeout=120)
            if proc.returncode != 0:
                tail = (proc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
                reason = tail[-1] if tail else "ffmpeg exited %d" % proc.returncode
                return [], "frames could not be extracted (%s); the manifest still describes the clip" % reason[:160]
            out = []
            for name in sorted(os.listdir(tmp)):
                if not name.endswith(".jpg"):
                    continue
                with open(os.path.join(tmp, name), "rb") as fh:
                    out.append({
                        "kind": "image",
                        "mime": "image/jpeg",
                        "name": name,
                        "dataUrl": _data_url("image/jpeg", fh.read()),
                    })
            if not out:
                return [], "frames could not be extracted (no frame was produced); the manifest still describes the clip"
            return out, ("%d frame(s) extracted from the clip and ready to paste" % len(out))
        except subprocess.TimeoutExpired:
            return [], "frame extraction timed out; the manifest still describes the clip"
        except Exception as exc:
            return [], "frame extraction failed (%s); the manifest still describes the clip" % type(exc).__name__
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ── manifest ─────────────────────────────────────────────────────────
    def manifest(self, rec, payloads, note):
        """A short plain-text description the model can read. Deliberately
        describes WHAT IS KNOWN and WHAT IS NOT - it never invents a frame
        count or a duration, and it tells the model to ask when it needs to
        see something the relay could not carry."""
        lines = []
        lines.append("MEDIA RELAY")
        article = "an" if rec["kind"] in ("image",) else "a"
        lines.append("The user attached %s %s file." % (article, rec["kind"]))
        lines.append("- name: %s" % rec["name"])
        lines.append("- type: %s" % rec["mime"])
        lines.append("- size: %.2f MB" % (rec["bytes"] / 1048576.0))
        duration = _probe_duration(rec["path"]) if rec["kind"] == "video" else None
        if duration:
            lines.append("- duration: %.1f s" % duration)
        frames = sum(1 for p in payloads if p.get("kind") == "image")
        if frames:
            lines.append("- pasted into this message: %d image(s)%s"
                         % (frames, " (extracted frames)" if rec["kind"] == "video" else ""))
        lines.append("- relay note: %s" % note)
        lines.append("Treat the pasted image(s) as the primary evidence. If the "
                     "attached media is a video and only frames were carried, say "
                     "which moment matters to you and ask the user to re-share that "
                     "moment as a still - do not guess what happened between frames.")
        return "\n".join(lines)

    # ── release ──────────────────────────────────────────────────────────
    def release(self, item_id: str) -> bool:
        with self._lock:
            existed = item_id in self._items
            self._unlink_locked(item_id)
        return existed

    def release_all(self):
        with self._lock:
            for i in list(self._items):
                self._unlink_locked(i)

    # ── introspection ────────────────────────────────────────────────────
    def list_items(self):
        with self._lock:
            self._sweep_locked()
            return [self._public(it) for it in self._items.values()]

    def stats(self):
        with self._lock:
            total = sum(it["bytes"] for it in self._items.values())
            return {
                "items": len(self._items),
                "spoolBytes": total,
                "maxItemBytes": MAX_ITEM_BYTES,
                "maxSpoolBytes": MAX_SPOOL_BYTES,
                "maxFrames": MAX_FRAMES,
                "ffmpeg": bool(shutil.which("ffmpeg")),
                "acceptedImageTypes": sorted({m for _e, m, _k, _t in IMAGE_TYPES}),
                "acceptedVideoTypes": sorted({m for _e, m, _k, _t in VIDEO_TYPES} | {MOV_TYPE[1]}),
                "spool": self._spool,
            }

    def _public(self, rec):
        return {
            "id": rec["id"],
            "kind": rec["kind"],
            "mime": rec["mime"],
            "name": rec["name"],
            "bytes": rec["bytes"],
            "ageSeconds": round(time.time() - rec["created"], 1),
        }


# ── helpers ───────────────────────────────────────────────────────────────

_NAME_UNSAFE = re.compile(r"[^A-Za-z0-9._\- ]+")
# A run of two or more dots is never a legitimate part of a display name and is
# exactly what a traversal or a hidden-file trick looks like. "." is kept for
# the extension, so the runs are collapsed explicitly rather than by charset.
_DOT_RUN = re.compile(r"\.{2,}")


def _safe_display_name(claimed, ext):
    """A bounded, display-only name. The client's name is never used as a
    filesystem path - only as a label - so this cannot traverse anywhere.
    It is sanitised anyway, because the label is also what the user reads in
    the panel, and "../../etc/passwd" shown as a filename is alarming even
    when harmless."""
    raw = str(claimed or "").strip()
    if not raw:
        return "attachment." + ext
    raw = raw.replace("\\", "/")
    raw = raw.rsplit("/", 1)[-1]          # drop any directory part, whatever the slash
    raw = _NAME_UNSAFE.sub("_", raw)[:120]
    raw = _DOT_RUN.sub(".", raw).strip(". ")
    if not raw:
        return "attachment." + ext
    if not raw.lower().endswith("." + ext):
        raw = os.path.splitext(raw)[0][:100] + "." + ext
    return raw or ("attachment." + ext)


def _data_url(mime, data):
    return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))


def _probe_duration(path):
    """Seconds, or None. Uses ffprobe when present; never guesses."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, timeout=30,
        )
        if proc.returncode == 0:
            return float(proc.stdout.decode("utf-8", "replace").strip())
    except Exception:
        pass
    return None


def decode_chunk(b64_text: str) -> bytes:
    """Decode one base64 chunk from a client, tolerating a data: prefix and
    URL-safe alphabet. Raises RelayError with a readable reason on garbage."""
    s = str(b64_text or "").strip()
    if s.startswith("data:"):
        comma = s.find(",")
        if comma == -1:
            raise RelayError("malformed data URL: no comma")
        s = s[comma + 1:]
    if not s:
        return b""
    try:
        return base64.b64decode(s, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise RelayError("chunk is not valid base64 (%s)" % type(exc).__name__)


# ── module-level singleton ────────────────────────────────────────────────
# bridge.py imports this once and reuses it, so the spool bookkeeping (and the
# sweep clock) is process-wide.
RELAY = MediaRelay()
