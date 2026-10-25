"""Run generated Roblox programs inside lupa with tests/fixtures/roblox_mock.lua."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def available():
    try:
        import lupa  # noqa: F401
        return True
    except Exception:
        return False


class LuauMock:
    def __init__(self, T, ctx):
        from lupa import LuaRuntime
        self.LuaRuntime = LuaRuntime
        self.T = T
        self.ctx = ctx
        self.src = (ROOT / "tests" / "fixtures" / "roblox_mock.lua").read_text(encoding="utf-8")

    def to_lua(self, rt, v):
        if isinstance(v, dict):
            return rt.table_from({k: self.to_lua(rt, x) for k, x in v.items()})
        if isinstance(v, list):
            return rt.table_from([self.to_lua(rt, x) for x in v])
        return v

    def from_lua(self, v):
        if hasattr(v, "items"):
            items = list(v.items())
            if items and all(isinstance(k, int) for k, _ in items) and sorted(k for k, _ in items) == list(range(1, len(items) + 1)):
                return [self.from_lua(x) for _, x in sorted(items)]
            return {str(k): self.from_lua(x) for k, x in items}
        return v

    def runtime(self, setup=None):
        rt = self.LuaRuntime(unpack_returned_tuples=True)
        rt.globals().JSON_DECODE = lambda s: self.to_lua(rt, json.loads(s))
        rt.globals().JSON_ENCODE = lambda t: json.dumps(self.from_lua(t))
        rt.globals().print = lambda *a: None
        rt.execute(self.src)
        if setup:
            rt.execute(setup)
        return rt

    def run(self, name, args, setup=None, rt=None):
        rt = rt or self.runtime(setup)
        d = json.loads(self.T.run(name, dict(args, dry_run=True), self.ctx)["text"])
        if not d.get("code"):
            return {"ok": False, "error": "no code: " + json.dumps(d)[:300]}, rt
        out = rt.execute(d["code"])
        return self.T.extract_result(str(out)), rt

    def probe(self, rt, code):
        """Evaluate a Lua chunk and return its result converted to Python."""
        return self.from_lua(rt.execute(code))
