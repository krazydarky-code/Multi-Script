"""Media relay - staging, sniffing, policy and payload construction.

The relay is what lets a user hand a photo or a clip to a chat surface that has
no upload control. It is also the one place in the bridge that writes
client-supplied bytes to disk, so the assertions here are as much about what it
REFUSES as about what it accepts.

Sections:
  1. sniff() identifies type from the bytes, never from a name
  2. stage() accepts the allow-list and records an honest descriptor
  3. stage() refuses an executable wearing a .png name
  4. stage() refuses an oversized item with a readable message
  5. prepare() on an image yields exactly one pasteable image payload
  6. prepare() on a video without ffmpeg still succeeds (manifest-only)
  7. the manifest never claims a frame it does not have
  8. release() removes the spooled bytes; list_items() reflects it
  9. the spool ceiling evicts oldest-first rather than growing without bound
 10. the display name is sanitised and cannot traverse the filesystem
 11. decode_chunk() accepts a data URL and rejects garbage readably
"""
import importlib.util
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
import media_relay  # noqa: E402

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f5e0000000049454e44ae426082"
)
JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 40
GIF = b"GIF89a" + b"\x00" * 40
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 40
BMP = b"BM" + b"\x00" * 40
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00" + b"\x00" * 40
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 40
AVI = b"RIFF\x00\x00\x00\x00AVI " + b"\x00" * 40

passed = 0


def ok(msg):
    global passed
    passed += 1
    print("  ok  " + msg)


def fresh():
    """A relay with its own spool so tests never touch the real one."""
    import tempfile
    return media_relay.MediaRelay(spool=tempfile.mkdtemp(prefix="zs-test-relay-"))


# ── 1. sniff ─────────────────────────────────────────────────────────────
cases = [
    (PNG, "png", "image/png", "image"),
    (JPG, "jpeg", "image/jpeg", "image"),
    (GIF, "gif", "image/gif", "image"),
    (WEBP, "webp", "image/webp", "image"),
    (BMP, "bmp", "image/bmp", "image"),
    (MP4, "mp4", "video/mp4", "video"),
    (WEBM, "webm", "video/webm", "video"),
    (AVI, "avi", "video/x-msvideo", "video"),
]
for blob, ext, mime, kind in cases:
    got = media_relay.sniff(blob)
    assert got == (ext, mime, kind), (ext, got)
assert media_relay.sniff(b"MZ\x90\x00")[2] == "unknown"
assert media_relay.sniff(b"")[2] == "unknown"
ok("sniff() identifies type from the bytes, never from a name")

# ── 2. stage accepts ─────────────────────────────────────────────────────
r = fresh()
item = r.stage(PNG, "shot.png", "image/png")
assert item["kind"] == "image" and item["mime"] == "image/png"
assert item["bytes"] == len(PNG)
assert item["id"] and len(item["id"]) == 16
assert "path" not in item, "the public descriptor must not leak the spool path"
ok("stage() accepts the allow-list and records an honest descriptor")

# ── 3. refuses a disguised executable ────────────────────────────────────
r = fresh()
try:
    r.stage(b"MZ\x90\x00\x03\x00\x00\x00not really a png", "innocent.png", "image/png")
    raise AssertionError("a disguised executable was accepted")
except media_relay.RelayError as exc:
    assert "supported" in str(exc)
ok("stage() refuses an executable wearing a .png name")

# ── 4. refuses oversized ─────────────────────────────────────────────────
r = fresh()
big = PNG + b"\x00" * (media_relay.MAX_ITEM_BYTES + 1 - len(PNG))
try:
    r.stage(big, "huge.png", "image/png")
    raise AssertionError("an oversized item was accepted")
except media_relay.RelayError as exc:
    assert "MB" in str(exc) and "relay accepts up to" in str(exc)
ok("stage() refuses an oversized item with a readable message")

# ── 5. image prepare ─────────────────────────────────────────────────────
r = fresh()
it = r.stage(PNG, "ui.png")
prep = r.prepare(it["id"])
assert len(prep["payloads"]) == 1
p = prep["payloads"][0]
assert p["kind"] == "image" and p["mime"] == "image/png"
assert p["dataUrl"].startswith("data:image/png;base64,")
# the data URL must decode back to the exact bytes we staged
import base64 as _b64
assert _b64.b64decode(p["dataUrl"].split(",", 1)[1]) == PNG
ok("prepare() on an image yields exactly one pasteable image payload")

# ── 6. video without ffmpeg still succeeds ───────────────────────────────
import shutil as _shutil
r = fresh()
vit = r.stage(MP4, "glitch.mp4")
prep = r.prepare(vit["id"])
assert prep["kind"] == "video"
if not _shutil.which("ffmpeg"):
    assert prep["payloads"] == [], "no frames should be claimed without ffmpeg"
    assert "ffmpeg is not installed" in prep["note"]
ok("prepare() on a video without ffmpeg still succeeds (manifest-only)")

# ── 7. manifest never claims an absent frame ─────────────────────────────
m = r.manifest(
    {"kind": "video", "name": "glitch.mp4", "mime": "video/mp4", "bytes": 12345,
     "path": os.path.join(r._spool, "does-not-exist.mp4")},
    [], "no frames were extracted because ffmpeg is not installed",
)
assert "pasted into this message" not in m, "manifest invented a pasted frame count"
assert "no frames were extracted" in m
assert "do not guess what happened between frames" in m
ok("the manifest never claims a frame it does not have")

# ── 8. release ───────────────────────────────────────────────────────────
r = fresh()
it = r.stage(PNG, "a.png")
path = r._items[it["id"]]["path"]
assert os.path.exists(path)
assert r.release(it["id"]) is True
assert not os.path.exists(path), "release() left the bytes on disk"
assert r.list_items() == []
assert r.release(it["id"]) is False, "releasing twice should report False"
ok("release() removes the spooled bytes; list_items() reflects it")

# ── 9. spool ceiling evicts oldest-first ─────────────────────────────────
r = fresh()
# Shrink the ceilings for the test rather than staging 96 MB of real bytes.
orig_count, orig_bytes = media_relay.MAX_ITEM_COUNT, media_relay.MAX_SPOOL_BYTES
media_relay.MAX_ITEM_COUNT, media_relay.MAX_SPOOL_BYTES = 3, 10 ** 9
try:
    ids = [r.stage(PNG, "f%d.png" % i)["id"] for i in range(6)]
    kept = {i["id"] for i in r.list_items()}
    assert len(kept) == 3, kept
    assert ids[-1] in kept, "the newest item was evicted"
    assert ids[0] not in kept, "the oldest item survived the ceiling"
finally:
    media_relay.MAX_ITEM_COUNT, media_relay.MAX_SPOOL_BYTES = orig_count, orig_bytes
ok("the spool ceiling evicts oldest-first rather than growing without bound")

# ── 10. display-name sanitisation ────────────────────────────────────────
assert ".." not in media_relay._safe_display_name("../../etc/passwd.png", "png")
assert "/" not in media_relay._safe_display_name("a/b/c.png", "png")
assert "\\" not in media_relay._safe_display_name("C:\\evil\\.png", "png")
assert media_relay._safe_display_name("", "png") == "attachment.png"
assert len(media_relay._safe_display_name("x" * 500 + ".png", "png")) <= 120
# a claimed name whose extension lies is corrected to the sniffed one
assert media_relay._safe_display_name("clip.exe", "mp4").endswith(".mp4")
ok("the display name is sanitised and cannot traverse the filesystem")

# ── 11. decode_chunk ─────────────────────────────────────────────────────
assert media_relay.decode_chunk("") == b""
assert media_relay.decode_chunk(_b64.b64encode(PNG).decode()) == PNG
assert media_relay.decode_chunk("data:image/png;base64," + _b64.b64encode(PNG).decode()) == PNG
try:
    media_relay.decode_chunk("data:image/png;base64")  # no comma
    raise AssertionError("a comma-less data URL was accepted")
except media_relay.RelayError as exc:
    assert "comma" in str(exc)
ok("decode_chunk() accepts a data URL and rejects garbage readably")

# ── bonus: stats reports the real ceilings ───────────────────────────────
r = fresh()
s = r.stats()
assert s["maxItemBytes"] == media_relay.MAX_ITEM_BYTES
assert s["maxFrames"] == media_relay.MAX_FRAMES
assert "image/png" in s["acceptedImageTypes"]
assert "video/mp4" in s["acceptedVideoTypes"]
assert isinstance(s["ffmpeg"], bool)
ok("stats() reports the real policy and ffmpeg availability")

# ── bridge integration ───────────────────────────────────────────────────
# The relay is useless if the bridge cannot reach it, so the wiring is pinned
# here too: the module must import regardless of the launcher's cwd, the routes
# must exist, and the model-facing tool must be registered.
import importlib.util as _ilu
import json as _json
import types as _types

_w = _types.ModuleType("websockets")
_w.ConnectionClosed = Exception
sys.modules.setdefault("websockets", _w)
_spec = _ilu.spec_from_file_location("ms_bridge_media", ROOT / "runtime" / "bridge.py")
_bridge = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_bridge)

assert _bridge.MEDIA_RELAY is not None, "bridge could not import the relay: %s" % _bridge.MEDIA_RELAY_ERROR
assert "ms_media_relay" in _bridge.BUILTIN_TOOL_NAMES, "the relay tool is not registered"
ok("bridge imports the relay and registers ms_media_relay")

# stats route
_st, _body = _bridge._handle_media_request("GET", "/media/stats", b"")
assert _st == 200
assert _json.loads(_body)["maxItemBytes"] == media_relay.MAX_ITEM_BYTES

# stage -> prepare -> release, exactly the path the extension will use
_env = _json.dumps({
    "name": "shot.png",
    "dataUrl": "data:image/png;base64," + _b64.b64encode(PNG).decode(),
}).encode()
_st, _body = _bridge._handle_media_request("POST", "/media/stage", _env)
assert _st == 200, _body
_iid = _json.loads(_body)["item"]["id"]
_st, _body = _bridge._handle_media_request("POST", "/media/prepare", _json.dumps({"id": _iid}).encode())
assert _st == 200, _body
assert len(_json.loads(_body)["prepared"]["payloads"]) == 1
_st, _body = _bridge._handle_media_request("POST", "/media/release", _json.dumps({"id": _iid}).encode())
assert _st == 200 and _json.loads(_body)["released"] == 1
ok("the /media stage -> prepare -> release route chain works")

# refusals are 400 with a readable message; an unknown route is 404; an
# oversized body is refused by the caller's cap, not silently truncated.
_st, _body = _bridge._handle_media_request("POST", "/media/stage", b"{}")
assert _st == 400 and "no media bytes" in _json.loads(_body)["error"]
assert _bridge._handle_media_request("GET", "/media/nope", b"")[0] == 404
# a disguised executable through the route is a 400, not a 500
_bad = _json.dumps({"name": "x.png", "dataUrl": "data:image/png;base64," + _b64.b64encode(b"MZ\x90\x00").decode()}).encode()
_st, _body = _bridge._handle_media_request("POST", "/media/stage", _bad)
assert _st == 400 and "supported" in _json.loads(_body)["error"]
ok("media routes refuse bad input with a 400 and a readable message")

# the model-facing tool answers stats/list/release and rejects an unknown action
class _M:
    def health(self):
        return []

_txt = _json.loads(_bridge._builtin_call("ms_media_relay", {"action": "stats"}, _M())["text"])
assert _txt["available"] is True and _txt["maxItemBytes"] == media_relay.MAX_ITEM_BYTES
assert "count" in _json.loads(_bridge._builtin_call("ms_media_relay", {"action": "list"}, _M())["text"])
assert "released" in _json.loads(_bridge._builtin_call("ms_media_relay", {"action": "release"}, _M())["text"])
try:
    _bridge._builtin_call("ms_media_relay", {"action": "explode"}, _M())
    raise AssertionError("an unknown relay action was accepted")
except RuntimeError as exc:
    assert "unknown media relay action" in str(exc)
ok("ms_media_relay answers stats/list/release and rejects an unknown action")

print("\ntest_media_relay: %d sections passed" % (passed + 1))
