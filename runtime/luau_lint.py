# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline Luau analyzer for Roblox code (standard library only).

Finds the mistakes that break Roblox games before they reach Studio:
  syntax    unbalanced blocks, `if` without `then`, loops without `do`, `=` used as a comparison,
            `!=`, stray characters, unfinished strings and comments
  scope     undefined variables (typos), assignments that create accidental globals, unused locals
  context   server-only APIs in client code and client-only APIs in server code
  patterns  endless loops with no yield, Connect(f()) / pcall(f()) calling too early, strings joined
            with +, unchecked RemoteEvent arguments, FindFirstChild used without a nil check,
            Instance.new with a parent argument
It is a careful heuristic, not a compiler: it never runs code and prefers missing a problem to
inventing one. Type annotations, generics, string interpolation, if-expressions, attributes and
compound assignment are understood.
"""
import difflib, re

KEYWORDS = {'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for', 'function', 'if', 'in', 'local', 'nil', 'not',
            'or', 'repeat', 'return', 'then', 'true', 'until', 'while'}
OPS = ['...', '..=', '//=', '==', '~=', '<=', '>=', '+=', '-=', '*=', '/=', '%=', '^=', '//', '..', '::', '->',
       '+', '-', '*', '/', '%', '^', '#', '&', '|', '~', '<', '>', '=', '(', ')', '{', '}', '[', ']', ';', ':', ',', '.', '?', '@']
BASE_GLOBALS = {'game', 'workspace', 'script', 'plugin', 'shared', '_G', '_VERSION', 'Enum', 'Instance', 'typeof', 'require',
                'math', 'string', 'table', 'coroutine', 'os', 'debug', 'utf8', 'bit32', 'task', 'buffer', 'vector',
                'print', 'warn', 'error', 'assert', 'pcall', 'xpcall', 'select', 'type', 'tostring', 'tonumber', 'ipairs',
                'pairs', 'next', 'rawget', 'rawset', 'rawequal', 'rawlen', 'setmetatable', 'getmetatable', 'unpack',
                'newproxy', 'gcinfo', 'collectgarbage', 'tick', 'time', 'elapsedTime', 'wait', 'spawn', 'delay', 'settings',
                'UserSettings', 'stats', 'version', 'printidentity', 'ypcall', 'loadstring', 'getfenv', 'setfenv',
                'DebuggerManager', 'PluginManager', 'Game', 'Workspace'}
STMT_KW = {'local', 'return', 'if', 'for', 'while', 'repeat', 'do', 'end', 'until', 'else', 'elseif', 'function', 'break'}
# `if` after one of these is an if-expression (no `end`)
EXPR_BEFORE = {'=', '(', ',', '{', '[', '==', '~=', '<=', '>=', '<', '>', '..', '+', '-', '*', '/', '//', '%', '^', '#',
               '+=', '-=', '*=', '/=', '%=', '^=', '..=', '//=', 'and', 'or', 'not', 'return', 'in', '::'}

class Tok:
    __slots__ = ('t', 'v', 'line')
    def __init__(self, t, v, line): self.t, self.v, self.line = t, v, line
    def __repr__(self): return f'{self.t}:{self.v}@{self.line}'

def tokenize(src, line=1, out=None, problems=None):
    out = [] if out is None else out
    problems = [] if problems is None else problems
    i, n = 0, len(src)
    def long_bracket(j):
        m = re.match(r'\[(=*)\[', src[j:j + 64])
        if not m: return None
        close = ']' + m.group(1) + ']'
        return j + len(m.group(0)), src.find(close, j + len(m.group(0))), len(close)
    while i < n:
        c = src[i]
        if c == '\n': line += 1; i += 1; continue
        if c in ' \t\r\f\v': i += 1; continue
        if src.startswith('--', i):
            lb = long_bracket(i + 2)
            if lb:
                start, k, cl = lb
                if k < 0: problems.append((line, 'syntax', 'error', 'A --[[ comment is never closed.')); return out, problems
                line += src.count('\n', i, k); i = k + cl; continue
            k = src.find('\n', i); i = n if k < 0 else k; continue
        if c.isalpha() or c == '_':
            m = re.match(r'[A-Za-z_][A-Za-z0-9_]*', src[i:i + 256]); w = m.group(0)
            out.append(Tok('kw' if w in KEYWORDS else 'name', w, line)); i += len(w); continue
        if c.isdigit() or (c == '.' and i + 1 < n and src[i + 1].isdigit()):
            m = re.match(r'0[xX][0-9a-fA-F_]+|0[bB][01_]+|(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?\d+)?', src[i:i + 128])
            out.append(Tok('num', m.group(0), line)); i += len(m.group(0)); continue
        if c in '"\'':
            j = i + 1
            while j < n and src[j] != c and src[j] != '\n':
                if src[j] == '\\':
                    if src.startswith('\\z', j):
                        j += 2
                        while j < n and src[j] in ' \t\r\n':
                            if src[j] == '\n': line += 1
                            j += 1
                        continue
                    if j + 1 < n and src[j + 1] == '\n': line += 1
                    j += 2; continue
                j += 1
            if j >= n or src[j] != c:
                problems.append((line, 'syntax', 'error', 'A string is not closed on this line.'))
                out.append(Tok('str', '', line)); i = j; continue
            out.append(Tok('str', src[i + 1:j], line)); i = j + 1; continue
        if c == '`':
            j = i + 1
            out.append(Tok('str', '`', line))
            while j < n and src[j] != '`':
                if src[j] == '\\': j += 2; continue
                if src[j] == '\n': line += 1
                if src[j] == '{':
                    depth, k = 1, j + 1
                    while k < n and depth:
                        if src[k] == '{': depth += 1
                        elif src[k] == '}': depth -= 1
                        elif src[k] in '"\'':
                            q = src[k]; k += 1
                            while k < n and src[k] != q and src[k] != '\n': k += 2 if src[k] == '\\' else 1
                        k += 1
                    inner = src[j + 1:k - 1]
                    out.append(Tok('op', '..', line)); out.append(Tok('op', '(', line))
                    tokenize(inner, line, out, problems)
                    out.append(Tok('op', ')', line)); out.append(Tok('op', '..', line)); out.append(Tok('str', '', line))
                    line += inner.count('\n'); j = k; continue
                j += 1
            if j >= n: problems.append((line, 'syntax', 'error', 'A `backtick` string is not closed.')); return out, problems
            i = j + 1; continue
        if c == '[':
            lb = long_bracket(i)
            if lb:
                start, k, cl = lb
                if k < 0: problems.append((line, 'syntax', 'error', 'A [[ string is never closed.')); return out, problems
                out.append(Tok('str', src[start:k], line)); line += src.count('\n', i, k); i = k + cl; continue
        for op in OPS:
            if src.startswith(op, i):
                out.append(Tok('op', op, line)); i += len(op); break
        else:
            if src.startswith('!=', i):
                problems.append((line, 'syntax', 'error', '`!=` is not Luau; use `~=` for "not equal".')); out.append(Tok('op', '~=', line)); i += 2; continue
            if src.startswith('&&', i) or src.startswith('||', i):
                pass
            problems.append((line, 'syntax', 'error', f'Unexpected character {c!r}.')); i += 1
    return out, problems

class Scope:
    __slots__ = ('names', 'parent', 'kind')
    def __init__(self, parent, kind): self.names, self.parent, self.kind = {}, parent, kind

class Analyzer:
    def __init__(self, toks, known, problems):
        self.toks, self.known, self.p = toks, known, problems
        self.i = 0
        self.scope = Scope(None, 'chunk')
        self.blocks = []        # [kind, line]
        self.globals_set = set()
        self.until_pop = None   # line of an `until` whose scope closes after that line

    # ---------- helpers
    def tk(self, k=0):
        j = self.i + k
        if 0 <= j < len(self.toks): return self.toks[j]
        return Tok('eof', '', self.toks[-1].line if self.toks else 1)
    def prev(self):
        return self.toks[self.i - 1] if self.i > 0 else None
    def is_op(self, t, *vals): return t.t == 'op' and t.v in vals
    def is_kw(self, t, *vals): return t.t == 'kw' and t.v in vals
    def add(self, line, kind, sev, msg): self.p.append((line, kind, sev, msg))
    def declare(self, name, line, kind='local'):
        self.scope.names[name] = {'name': name, 'line': line, 'reads': 0, 'kind': kind}
    def lookup(self, name):
        s = self.scope
        while s:
            if name in s.names: return s.names[name]
            s = s.parent
        return None
    def push(self, kind, line):
        self.blocks.append([kind, line]); self.scope = Scope(self.scope, kind)
    def report_unused(self, scope):
        for rec in scope.names.values():
            if rec['reads'] == 0 and rec['kind'] in ('local', 'function') and not rec['name'].startswith('_'):
                self.add(rec['line'], 'unused', 'info', f'`{rec["name"]}` is declared but never used.')
    def pop(self, line):
        if not self.blocks:
            self.add(line, 'syntax', 'error', '`end` without a matching block (one `end` too many).'); return
        self.report_unused(self.scope)
        self.blocks.pop(); self.scope = self.scope.parent or self.scope
    def statement_start(self):
        p = self.prev()
        if p is None: return True
        if p.t in ('name', 'num', 'str'): return True
        if p.t == 'kw' and p.v in ('end', 'true', 'false', 'nil', 'break', 'do', 'then', 'else', 'repeat'): return True
        if p.t == 'op' and p.v in (')', ']', '}', ';', '...'): return True
        return False
    def read(self, t):
        rec = self.lookup(t.v)
        if rec: rec['reads'] += 1; return
        if t.v == 'self':
            self.add(t.line, 'scope', 'warning', '`self` is used outside a method (define the function with `:`).'); return
        if t.v in self.known or t.v in self.globals_set: return
        cands = set(self.globals_set)
        s = self.scope
        while s: cands |= set(s.names); s = s.parent
        sug = difflib.get_close_matches(t.v, list(cands) + [k for k in self.known if k[:1].lower() == t.v[:1].lower()], n=1, cutoff=0.8)
        self.add(t.line, 'undefined', 'error', f'`{t.v}` is not defined here' + (f'; did you mean `{sug[0]}`?' if sug else ' (missing `local`, a typo, or used outside its scope).'))
    def in_table(self):
        depth = 0
        for j in range(self.i - 1, -1, -1):
            tok = self.toks[j]
            if tok.t != 'op': continue
            if tok.v in (')', ']', '}'): depth += 1
            elif tok.v in ('(', '['):
                if depth == 0: return False
                depth -= 1
            elif tok.v == '{':
                if depth == 0: return True
                depth -= 1
        return False
    def is_key(self):
        p, nx = self.prev(), self.tk(1)
        return p is not None and self.is_op(p, '{', ',', ';') and self.is_op(nx, '=') and self.in_table()
    def name_ref(self, t):
        """Handle a NAME seen in expression context."""
        p = self.prev()
        if p is not None and self.is_op(p, '.', ':'): return
        if self.is_key(): return
        self.read(t)

    # ---------- types
    def skip_type(self):
        """Consume one type expression (annotation, cast, alias body)."""
        depth, start = 0, self.i
        while self.tk().t != 'eof':
            t = self.tk()
            if t.t == 'op' and t.v in ('(', '{', '[', '<'):
                depth += 1; self.i += 1; continue
            if t.t == 'op' and t.v in (')', '}', ']', '>'):
                if depth == 0: return
                depth -= 1; self.i += 1; continue
            if depth == 0:
                if t.t == 'op' and t.v not in ('|', '&', '?', '.', '...', '->', '-'): return
                if t.t == 'op' and t.v == '-' and not self.is_op(self.tk(1), '>'): return
                if t.t == 'kw' and t.v not in ('nil', 'true', 'false', 'function'): return
                if self.i > start:
                    p = self.prev()
                    joins = p.t == 'op' and p.v in ('|', '&', '.', '->', '...', '-', '>')
                    if t.t in ('name', 'kw', 'str', 'num') and not joins and not (p.t == 'op' and p.v in ('(', '{', '[', '<')):
                        if not (p.t == 'name' and p.v in ('typeof', 'keyof', 'rawkeyof') ):
                            return
            self.i += 1
    def skip_generics(self):
        if self.is_op(self.tk(), '<'):
            depth = 0
            while self.tk().t != 'eof':
                v = self.tk().v
                if v == '<': depth += 1
                elif v == '>': depth -= 1
                self.i += 1
                if depth == 0: return

    # ---------- functions
    def function_body(self, line, method=False):
        self.skip_generics()
        self.push('function', line)
        if method: self.declare('self', line, 'param')
        if not self.is_op(self.tk(), '('):
            self.add(self.tk().line, 'syntax', 'error', 'A function needs `(` for its parameters.'); return
        self.i += 1
        while self.tk().t != 'eof':
            t = self.tk()
            if self.is_op(t, ')'): self.i += 1; break
            if t.t == 'name': self.declare(t.v, t.line, 'param'); self.i += 1
            elif self.is_op(t, '...'):
                self.declare('...', t.line, 'param'); self.i += 1
                if self.is_op(self.tk(), ':'): self.i += 1; self.skip_type()
            elif self.is_op(t, ':'): self.i += 1; self.skip_type()
            else: self.i += 1
        if self.is_op(self.tk(), ':'):
            self.i += 1; self.skip_type()
    def run_function_body(self):
        target = len(self.blocks) - 1
        while self.tk().t != 'eof' and len(self.blocks) > target:
            self.step()

    # ---------- expressions inside conditions / initializers
    def expression_until(self, stop_kws=(), start_line=None, stop_at_new_statement=True):
        depth = 0
        while self.tk().t != 'eof':
            t = self.tk()
            if self.is_op(t, '(', '{', '['): depth += 1
            elif self.is_op(t, ')', '}', ']'):
                if depth == 0: return t
                depth -= 1
            if depth == 0 and t.t == 'kw' and t.v in stop_kws: return t
            if depth == 0 and t.t == 'kw' and t.v in ('end', 'until', 'else', 'elseif', 'local', 'return', 'while', 'for', 'repeat', 'break') and t.v not in stop_kws:
                return t
            if depth == 0 and stop_at_new_statement and start_line is not None and t.t == 'name' and self.i > 0:
                pv = self.prev()
                if (pv.t in ('name', 'num', 'str') or (pv.t == 'kw' and pv.v in ('end', 'true', 'false', 'nil')) or (pv.t == 'op' and pv.v in (')', ']', '}', '...'))) and not (pv.t == 'str' and pv.v == '`'):
                    return t
            if depth == 0 and self.is_op(t, ';'): return t
            if depth == 0 and t.t == 'kw' and t.v in ('if', 'function', 'do') and t.v not in stop_kws:
                pv = self.prev()
                expr_pos = pv is not None and ((pv.t == 'op' and pv.v in EXPR_BEFORE) or (pv.t == 'kw' and pv.v in EXPR_BEFORE))
                if not expr_pos: return t
            if t.t == 'kw' and t.v == 'function':
                self.i += 1; self.function_body(t.line); self.run_function_body(); continue
            if t.t == 'kw' and t.v == 'if':   # if-expression
                self.i += 1; continue
            if t.t == 'name': self.name_ref(t)
            elif self.is_op(t, '::'): self.i += 1; self.skip_type(); continue
            elif self.is_op(t, '+') and (self.prev() is not None and self.prev().t == 'str' and self.prev().v != '' or self.tk(1).t == 'str' and self.tk(1).v not in ('', '`')):
                self.add(t.line, 'pattern', 'error', 'Strings are joined with `..` in Luau; `+` tries to do arithmetic.')
            self.i += 1
        return self.tk()

    def condition(self, closer, line):
        start = self.i
        while self.tk().t != 'eof':
            stop = self.expression_until(stop_kws=(closer,), start_line=None, stop_at_new_statement=False)
            if self.is_kw(stop, closer):
                for j in range(start, self.i):
                    tok = self.toks[j]
                    if self.is_op(tok, '='):
                        d = sum(1 if self.is_op(x, '(', '{', '[') else -1 if self.is_op(x, ')', '}', ']') else 0 for x in self.toks[start:j])
                        if d == 0: self.add(tok.line, 'syntax', 'error', 'A single `=` in a condition assigns; use `==` to compare.'); break
                self.i += 1; return
            if self.is_op(stop, ')', '}', ']'): self.i += 1; continue
            self.add(line, 'syntax', 'error', f'Missing `{closer}` after the condition that starts on line {line}.'); return
        self.add(line, 'syntax', 'error', f'Missing `{closer}` after the condition that starts on line {line}.')

    # ---------- statements
    def step(self):
        t = self.tk()
        if self.until_pop is not None and t.line > self.until_pop:
            closing = self.scope
            self.scope = self.scope.parent or self.scope; self.until_pop = None
            self.report_unused(closing)
        if self.is_op(t, '@'):   # attributes: @native, @checked, @[...]
            self.i += 1
            if self.is_op(self.tk(), '['):
                while self.tk().t != 'eof' and not self.is_op(self.tk(), ']'): self.i += 1
            self.i += 1; return
        if t.t == 'name' and t.v in ('type', 'export') and self.statement_start():
            j = 1
            if t.v == 'export':
                if not (self.tk(1).t == 'name' and self.tk(1).v == 'type'): return self._name_stmt(t)
                j = 2
            if self.tk(j).t == 'name' and self.is_op(self.tk(j + 1), '=', '<'):
                self.i += j + 1; self.skip_generics()
                if self.is_op(self.tk(), '='): self.i += 1
                self.skip_type(); return
            if self.tk(j).t == 'kw' and self.tk(j).v == 'function':   # type function
                self.i += j + 1
                if self.tk().t == 'name': self.i += 1
                self.function_body(t.line); return
        if t.t == 'name' and t.v == 'continue' and self.statement_start() and not self.is_op(self.tk(1), '(', '.', ':', '=', '['):
            self.i += 1; return
        if t.t == 'kw': return self._keyword(t)
        if self.is_op(t, '::'): self.i += 1; self.skip_type(); return
        if t.t == 'name': return self._name_stmt(t)
        if t.t == 'op' and t.v in ('+', '-') and self.i > 0:
            nx = self.tk(1); pv = self.prev()
            if (pv is not None and pv.t == 'str' and pv.v not in ('', '`')) or (nx.t == 'str' and nx.v not in ('', '`')):
                if t.v == '+': self.add(t.line, 'pattern', 'error', 'Strings are joined with `..` in Luau; `+` tries to do arithmetic.')
        self.i += 1

    def _name_stmt(self, t):
        p = self.prev()
        if p is not None and self.is_op(p, '.', ':'): self.i += 1; return
        if self.is_key(): self.i += 1; return
        if self.statement_start() and self.is_op(self.tk(1), '=', ','):
            j, names = self.i, []
            while j < len(self.toks) and self.toks[j].t == 'name':
                names.append(self.toks[j]); j += 1
                if j < len(self.toks) and self.is_op(self.toks[j], ','): j += 1; continue
                break
            if j < len(self.toks) and self.is_op(self.toks[j], '=') and names:
                self.i = j + 1
                for nm in names:
                    rec = self.lookup(nm.v)
                    if rec is None and nm.v not in self.known and nm.v not in self.globals_set:
                        self.add(nm.line, 'scope', 'warning', f'`{nm.v} = ...` creates a global variable. Add `local`, or fix the spelling of an existing variable.')
                        self.globals_set.add(nm.v)
                self.expression_until(start_line=self.tk(-1).line)
                return
        self.read(t); self.i += 1

    def _keyword(self, t):
        v = t.v
        if v == 'local':
            self.i += 1
            if self.is_kw(self.tk(), 'function'):
                self.i += 1; nm = self.tk()
                if nm.t == 'name': self.declare(nm.v, nm.line, 'function'); self.i += 1
                self.function_body(t.line); return
            names = []
            while self.tk().t == 'name':
                names.append(self.tk()); self.i += 1
                if self.is_op(self.tk(), '<'):
                    while self.tk().t != 'eof' and not self.is_op(self.tk(), '>'): self.i += 1
                    self.i += 1
                if self.is_op(self.tk(), ':'): self.i += 1; self.skip_type()
                if self.is_op(self.tk(), ','): self.i += 1; continue
                break
            if not names: self.add(t.line, 'syntax', 'error', '`local` must be followed by a name.')
            if self.is_op(self.tk(), '='):
                self.i += 1
                self.expression_until(start_line=t.line)
            for nm in names: self.declare(nm.v, nm.line, 'local')
            return
        if v == 'function':
            stmt = self.statement_start()
            self.i += 1
            nm = self.tk()
            if nm.t == 'name' and stmt:
                self.i += 1; method = False
                if self.is_op(self.tk(), '.', ':'):
                    self.read(nm)
                    while self.is_op(self.tk(), '.', ':'):
                        method = self.tk().v == ':'; self.i += 2
                else:
                    rec = self.lookup(nm.v)
                    if rec: rec['reads'] += 1
                    elif nm.v not in self.known: self.globals_set.add(nm.v)
                self.function_body(t.line, method); return
            self.function_body(t.line); return
        if v == 'if':
            p = self.prev()
            if p is not None and ((p.t == 'op' and p.v in EXPR_BEFORE) or (p.t == 'kw' and p.v in EXPR_BEFORE)):
                self.i += 1; return
            self.push('if', t.line); self.i += 1
            self.condition('then', t.line); return
        if v == 'elseif':
            if not self.blocks or self.blocks[-1][0] != 'if': self.add(t.line, 'syntax', 'error', '`elseif` without an open `if`.')
            else: self.report_unused(self.scope); self.scope = Scope(self.scope.parent, 'if')
            self.i += 1; self.condition('then', t.line); return
        if v == 'else':
            if self.blocks and self.blocks[-1][0] == 'if': self.report_unused(self.scope); self.scope = Scope(self.scope.parent, 'if')
            self.i += 1; return
        if v == 'while':
            self.i += 1; self.condition('do', t.line); self.push('while', t.line); self.blocks[-1].append(self.i); return
        if v == 'for':
            self.i += 1; names = []
            while self.tk().t == 'name':
                names.append(self.tk()); self.i += 1
                if self.is_op(self.tk(), ':'): self.i += 1; self.skip_type()
                if self.is_op(self.tk(), ','): self.i += 1; continue
                break
            if not names: self.add(t.line, 'syntax', 'error', '`for` must be followed by a loop variable.')
            if not (self.is_op(self.tk(), '=') or self.is_kw(self.tk(), 'in')):
                self.add(t.line, 'syntax', 'error', '`for` needs `=` (counting loop) or `in` (iterator loop).')
            else:
                self.i += 1
            self.condition('do', t.line)
            self.push('for', t.line)
            for nm in names: self.declare(nm.v, nm.line, 'loopvar')
            return
        if v == 'do': self.push('do', t.line); self.i += 1; return
        if v == 'repeat': self.push('repeat', t.line); self.i += 1; return
        if v == 'until':
            if not self.blocks or self.blocks[-1][0] != 'repeat': self.add(t.line, 'syntax', 'error', '`until` without a matching `repeat`.')
            else: self.blocks.pop(); self.until_pop = t.line
            self.i += 1
            self.expression_until(start_line=t.line); return
        if v == 'end':
            if self.blocks and self.blocks[-1][0] == 'while' and len(self.blocks[-1]) > 2:
                self._check_yield(self.blocks[-1])
            self.pop(t.line); self.i += 1; return
        if v == 'return':
            self.i += 1; self.expression_until(start_line=t.line); return
        self.i += 1

    def _check_yield(self, block):
        kind, line, start = block[0], block[1], block[2]
        cond = self.toks[max(0, start - 3):start]
        if not any(x.t == 'kw' and x.v == 'true' for x in cond): return
        body = self.toks[start:self.i]
        text = ' '.join(x.v for x in body)
        if not re.search(r'\bwait\b|\bWait\b|\bdefer\b|\byield\b|\bHeartbeat\b|\bRenderStepped\b|\bStepped\b|\bbreak\b|\breturn\b|Async\b|\bInvoke\w*\b|\bPreSimulation\b|\bPostSimulation\b|\bsleep\b', text):
            self.add(line, 'pattern', 'error', '`while true do` with no yield inside freezes the game; add `task.wait()` in the loop.')

    def run(self):
        guard = 0
        while self.i < len(self.toks):
            before = self.i
            self.step()
            if self.i == before:
                self.i += 1
            guard += 1
            if guard > 400000: break
        while self.blocks:
            kind, line = self.blocks.pop()[:2]
            self.add(line, 'syntax', 'error', f'This `{kind}` is never closed' + (' with `until`.' if kind == 'repeat' else ' with `end`.'))
        self.report_unused(self.scope)
        return self.p

# ------------------------------------------------------------------ context and pattern rules (line based, on comment-free text)
SERVER_ONLY = [
    (r'GetService\(\s*["\'](DataStoreService|MemoryStoreService|MessagingService|ServerStorage|ServerScriptService|AnalyticsService|BanService)["\']', 'uses {0}, which only works on the server'),
    (r'\.OnServerEvent\b|\.OnServerInvoke\b', 'handles a remote on the server side (OnServerEvent/OnServerInvoke)'),
    (r':FireClient\s*\(|:FireAllClients\s*\(|:InvokeClient\s*\(', 'fires to clients (FireClient/FireAllClients/InvokeClient)'),
    (r'\.ProcessReceipt\s*=', 'sets MarketplaceService.ProcessReceipt'),
    (r':AwardBadge\w*\s*\(|:BindToClose\s*\(', 'awards badges or binds shutdown'),
    (r':(?:GetAsync|PostAsync|RequestAsync)\s*\(', 'makes HttpService requests'),
]
CLIENT_ONLY = [
    (r'\bLocalPlayer\b', 'uses Players.LocalPlayer, which is nil on the server'),
    (r':FireServer\s*\(|:InvokeServer\s*\(', 'calls the server (FireServer/InvokeServer)'),
    (r'\.OnClientEvent\b|\.OnClientInvoke\b', 'handles a remote on the client side'),
    (r'\.RenderStepped\b|:BindToRenderStep\s*\(', 'runs on RenderStepped'),
    (r'GetService\(\s*["\'](UserInputService|ContextActionService|GuiService|HapticService|VRService)["\']', 'uses {0} (player input)'),
    (r':SetCore\s*\(|:SetCoreGuiEnabled\s*\(|:GetMouse\s*\(', 'changes the player\'s CoreGui or mouse'),
]

def context_rules(lines, context):
    out = []
    srv, cli = [], []
    for i, ln in enumerate(lines, 1):
        for rx, msg in SERVER_ONLY:
            m = re.search(rx, ln)
            if m: srv.append((i, msg.format(*(m.groups() or ('',)))))
        for rx, msg in CLIENT_ONLY:
            m = re.search(rx, ln)
            if m: cli.append((i, msg.format(*(m.groups() or ('',)))))
    if context == 'client':
        for ln, msg in srv: out.append((ln, 'context', 'error', f'This LocalScript {msg}; move that part to a server Script and talk to it with a RemoteEvent.'))
    elif context == 'server':
        for ln, msg in cli:
            sev = 'error' if 'LocalPlayer' in msg or 'FireServer' in msg or 'OnClientEvent' in msg else 'warning'
            out.append((ln, 'context', sev, f'This server Script {msg}; that belongs in a LocalScript.'))
    elif context in ('auto', '') and srv and cli:
        s, c = srv[0], cli[0]
        if not any('LocalPlayer' in m for _, m in cli) or any('DataStoreService' in m or 'OnServerEvent' in m or 'FireClient' in m for _, m in srv):
            out.append((c[0], 'context', 'warning', f'This code mixes client-only work (line {c[0]}: {c[1]}) with server-only work (line {s[0]}: {s[1]}). One script runs on one side; split it unless this is a ModuleScript used by both.'))
    return out

def pattern_rules(lines):
    out = []
    for i, ln in enumerate(lines, 1):
        m = re.search(r':Connect\s*\(\s*([A-Za-z_][\w.:]*)\s*\(', ln)
        if m and not ln[m.end(1):].lstrip().startswith('(function') and m.group(1) not in ('function',):
            out.append((i, 'pattern', 'error', f'`:Connect({m.group(1)}(...))` calls {m.group(1)} now and connects its result; pass the function itself or wrap it: `:Connect(function(...) {m.group(1)}(...) end)`.'))
        m = re.search(r'\b(pcall|task\.spawn|task\.defer|coroutine\.wrap)\s*\(\s*([A-Za-z_][\w.]*)\s*\(', ln)
        if m and m.group(2) != 'function':
            out.append((i, 'pattern', 'warning', f'`{m.group(1)}({m.group(2)}(...))` runs {m.group(2)} immediately; pass the function and its arguments separately: `{m.group(1)}({m.group(2)}, ...)`.'))
        m = re.search(r'task\.delay\s*\(\s*[^,]+,\s*([A-Za-z_][\w.]*)\s*\(', ln)
        if m and m.group(1) != 'function':
            out.append((i, 'pattern', 'warning', f'`task.delay(t, {m.group(1)}(...))` runs {m.group(1)} immediately; pass `task.delay(t, {m.group(1)}, ...)`.'))
        if re.search(r'Instance\.new\s*\(\s*["\'][A-Za-z]+["\']\s*,\s*[^)\s]', ln):
            out.append((i, 'pattern', 'warning', 'Instance.new with a parent argument; set the properties first and `.Parent` last.'))
        if re.search(r':FindFirstChild\w*\s*\([^()]*(?:\([^()]*\))?[^()]*\)\s*[.:]\s*[A-Za-z_]', ln) and not re.search(r'\b(?:if|and|or|assert)\b[^\n]*:FindFirstChild', ln):
            out.append((i, 'pattern', 'warning', 'The result of FindFirstChild is used without checking it; it is nil when nothing matches. Check it, or use WaitForChild for things that must exist.'))
        m = re.search(r'\.OnServerEvent\s*:\s*Connect\s*\(\s*function\s*\(\s*\)', ln)
        if m: out.append((i, 'pattern', 'error', 'This RemoteEvent handler ignores its first argument, the player who fired it; you cannot check who is asking.'))
    # remote handlers that never check their arguments
    for i, ln in enumerate(lines):
        m = re.search(r'\.OnServerEvent\s*:\s*Connect\s*\(\s*function\s*\(\s*\w+\s*,\s*(\w+)', ln)
        if m:
            block = '\n'.join(lines[i:i + 25])
            if not re.search(r'typeof\s*\(|\btype\s*\(|assert\s*\(|tonumber\s*\(|:IsA\s*\(|\bt\.\w+\s*\(|validate|check', block, re.I):
                out.append((i + 1, 'pattern', 'warning', f'The RemoteEvent handler uses `{m.group(1)}` from the client without checking its type or range. Never trust the client.'))
    return out

def strip_comments_keep_lines(src):
    out = re.sub(r'--\[(=*)\[.*?\]\1\]', lambda m: '\n' * m.group(0).count('\n'), src, flags=re.S)
    out = re.sub(r'--[^\n]*', '', out)
    return out

def mask_strings(src):
    """Replace string contents by spaces (same length and lines) so line rules do not match inside text."""
    def blank(m): return m.group(0)[0] + re.sub(r'[^\n]', ' ', m.group(0)[1:-1]) + m.group(0)[-1]
    out = re.sub(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'', blank, src)
    out = re.sub(r'\[(=*)\[.*?\]\1\]', lambda m: re.sub(r'[^\n]', ' ', m.group(0)), out, flags=re.S)
    return out

def analyze(src, known_globals=(), context='auto', want=('syntax', 'scope', 'context', 'pattern'), max_findings=150):
    """Return a list of findings: {line, kind, severity, message}."""
    if not isinstance(src, str): return []
    known = set(BASE_GLOBALS) | set(known_globals)
    problems = []
    toks, problems = tokenize(src, problems=problems)
    if 'syntax' in want or 'scope' in want:
        Analyzer(toks, known, problems).run()
    nocomment = strip_comments_keep_lines(src)
    clean = mask_strings(nocomment)
    lines = clean.split('\n')
    if 'context' in want: problems += context_rules(nocomment.split('\n'), context)
    if 'pattern' in want: problems += pattern_rules(lines)
    kinds_ok = set(want) | ({'undefined', 'unused'} if 'scope' in want else set())
    seen, out = set(), []
    order = {'error': 0, 'warning': 1, 'info': 2}
    for line, kind, sev, msg in sorted(problems, key=lambda x: (order.get(x[2], 3), x[0])):
        if kind not in kinds_ok: continue
        key = (line, msg)
        if key in seen: continue
        seen.add(key)
        out.append({'line': line, 'kind': kind, 'severity': sev, 'message': msg})
        if len(out) >= max_findings: break
    return sorted(out, key=lambda f: (f['line'], order.get(f['severity'], 3)))
