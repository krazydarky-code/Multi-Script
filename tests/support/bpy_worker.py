# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent headless-Blender worker (needs the `bpy` pip wheel). Reads one JSON object per
line on stdin ({"code": "..."}), exec()s it with bpy state preserved between calls, and writes
one JSON line {"out": "<captured stdout>", "err": "<traceback or empty>"} on the real stdout."""
import contextlib
import io
import json
import sys
import traceback

REAL_OUT = sys.stdout
import bpy  # noqa: E402,F401

bpy.ops.wm.read_factory_settings(use_empty=False)
REAL_OUT.write(json.dumps({"ready": True, "version": bpy.app.version_string}) + "\n")
REAL_OUT.flush()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    buf = io.StringIO()
    err = ""
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(msg["code"], "<ms>", "exec"), {"__name__": "__ms__"})
    except BaseException:
        err = traceback.format_exc()[-1500:]
    REAL_OUT.write(json.dumps({"out": buf.getvalue(), "err": err}) + "\n")
    REAL_OUT.flush()
