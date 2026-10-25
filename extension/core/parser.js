// SPDX-License-Identifier: GPL-3.0-or-later
// core/parser.js - Multi-Script command parsing. PURE string logic, zero DOM:
// the provider extracts a turn's text from the site's DOM; everything here
// operates on that text. The command formats (###LUA### blocks, {"command":…}
// JSON) are defined by OUR system prompt, so they are the same on every AI site
// - only the way a site's markdown may mangle them differs (the regexes below
// are whitespace/dash tolerant for that reason).
// eslint-disable-next-line no-unused-vars
const ZSParse = (() => {
  "use strict";

  const START_M = "###MCP_TOOL###";
  const END_M = "###END_MCP_TOOL###";
  // Whitespace-tolerant markers: site markdown can insert spaces around the
  // hashes (e.g. "### LUA ###") or render END_LUA with a dash. These regexes
  // match those variants so a marker mangled by markdown still parses.
  // The optional `:Edit|:Server|:Client` suffix selects the Roblox datamodel
  // execute_luau runs against (the MCP REQUIRES datamodel_type; a bare
  // ###LUA### defaults to "Edit" so the model never has to think about it
  // outside play-testing).
  const LUA_START_RE = /###\s*lua(?:\s*[:\-_ ]\s*(edit|client|server))?\s*(?:###|---)/i;
  const LUA_END_RE = /###\s*end[_\- ]?lua\s*###/i;
  const LUA_DEFAULT_DM = "Edit";
  const dmName = (m) => (m ? m[0].toUpperCase() + m.slice(1).toLowerCase() : LUA_DEFAULT_DM);

  // Find the first LUA start marker at or after `from`. Returns { pos, len, dm }
  // where len is the marker's own length to skip past it and dm the requested
  // datamodel ("Edit" when unspecified).
  function findLuaStart(text, from = 0) {
    const m = LUA_START_RE.exec(text.slice(from));
    return m ? { pos: from + m.index, len: m[0].length, dm: dmName(m[1]) } : { pos: -1, len: 0, dm: LUA_DEFAULT_DM };
  }

  // Find the first LUA end marker at or after `from`. Returns its start index or -1.
  function findLuaEnd(text, from = 0) {
    const m = LUA_END_RE.exec(text.slice(from));
    return m ? from + m.index : -1;
  }

  // Strip a code-block UI label (the "Copy" button caption, or a leftover fence
  // language token like "json") that some sites bleed into the block's text
  // right after the opening marker. Seen live on Kimi: its code-block chrome
  // renders as `###lua### Copy <code>`, so the bare-marker slice below would
  // capture `Copy task.wait(...)` as the Lua code - not valid Lua, so StudioMCP
  // rejects it with "Failed to parse command code". The JSON path already does
  // this at line ~206; mirror it for the raw ###LUA### extraction. Requires
  // trailing whitespace (\s+) so it never eats a legitimate identifier like
  // `Copy(x)` that a script might genuinely start with.
  function stripCodeChrome(code) {
    return code.replace(/^(?:json|copy)\s+/i, "");
  }

  // A command is `{"command":"name", ...}` (or "tool"). The params/arguments
  // object is OPTIONAL: paramless commands like list_commands are written as
  // `{"command":"list_commands"}`, so requiring "params" too would MISS them
  // (they'd be shown raw and never executed). We key on the `"command":"…"` /
  // `"tool":"…"` shape instead - a string-valued key, which prose almost never
  // contains - so paramless calls are detected without false-positiving on text.
  const CMD_KEY_RE = /"(?:command|tool)"\s*:\s*"/;

  // DeepSeek's OWN agentic tool-call markup ("DSML"), which it sometimes emits
  // instead of a Multi-Script command - seen live in user reports, DeepSeek only:
  //   <|DSML|>tool_calls>
  //   <|DSML|>invoke name="script_read">
  //   <|DSML|>parameter name="target_file" string="true">…</|DSML|>parameter>
  //   </|DSML|>tool_calls>
  // It carries no "command"/"tool" key and no ###…### markers, so every guard in
  // the classify ladder missed it and the turn finalized as a plain-text answer:
  // the tool never ran and the loop ended with the user watching a dead agent.
  // Matches the opener AND the closing "</|DSML|>…" form. Verified live
  // 2026-08-22: DeepSeek emits PLAIN ASCII bars, `<|DSML|>tool_calls>`. The
  // doubled "< |  | DSML |  |" seen in user screenshots is only how the site
  // RENDERS it, but the class is deliberately permissive - any run of bars and
  // spaces on either side - so a build that really does emit doubled or
  // full-width (U+FF5C) bars is covered too, without needing another sample. Deliberately NOT
  // gated on a known tool name: the degenerate case seen in the wild is a bare
  // `<|DSML|>tool_calls>` with no invoke and no name at all, and the marker
  // itself never occurs in ordinary prose.
  const DSML_RE = /<[\s\/]*[|｜][\s|｜]*DSML[\s|｜]*[|｜]/i;

  // Chat front-ends sometimes "prettify" the model's JSON: curly double quotes
  // (“command”) or single-quoted keys ('command'). The structural quotes are then
  // not ASCII and the call is never even detected. Fold them back - but ONLY when
  // there is no ASCII-quoted command/tool key at all, so code inside a valid call
  // (which may legitimately contain curly quotes in a string) is never rewritten.
  function foldTypography(text) {
    const t = String(text == null ? "" : text);
    if (/"(?:command|tool)"\s*:/.test(t)) return t;
    let out = t;
    if (/[\u201C\u201D\u201E]\s*(?:command|tool)\s*[\u201C\u201D]/.test(out)) out = out.replace(/[\u201C\u201D\u201E]/g, '"');
    if (/(?:^|[{,\s])'(?:command|tool)'\s*:/.test(out)) out = out.replace(/'(command|tool|params|arguments)'(\s*:)/g, '"$1"$2');
    return out;
  }

  function hasToolSignature(r) {
    r = foldTypography(r);
    return (
      r.includes(START_M) ||
      r.includes("MCP_TOOL") ||
      LUA_START_RE.test(r) ||
      CMD_KEY_RE.test(r) ||
      DSML_RE.test(r)
    );
  }

  // True if the reply contains a tool block that has STARTED but not yet CLOSED
  // (a ###LUA### / ###MCP_TOOL### opener with no matching end marker). Used by the
  // response watcher to avoid finalizing a command that is still being streamed.
  function hasOpenToolBlock(r) {
    r = foldTypography(r);
    if (!r) return false;
    const { pos: ls, len } = findLuaStart(r);
    if (ls !== -1 && findLuaEnd(r, ls + len) === -1) return true;
    const sm = r.indexOf(START_M);
    if (sm !== -1) {
      const low = r.toLowerCase();
      if (low.indexOf("###end_mcp_tool###", sm) === -1 && low.indexOf("###end-mcp_tool###", sm) === -1) return true;
    }
    // An inline JSON command ({"command"/"tool": …}) whose object has NOT closed yet
    // is still being streamed (a big multi_edit can take many seconds). Treat it as
    // open so the watcher keeps waiting instead of finalizing - and failing to parse -
    // half a command, which would drop the tool and end the turn as plain text.
    for (const key of ['"command"', '"tool"']) {
      const k = r.indexOf(key);
      if (k === -1) continue;
      const open = r.lastIndexOf("{", k);
      if (open !== -1 && matchBrace(r, open) === -1) return true;
    }
    return false;
  }

  // Normalise a parsed JSON object into { tool, arguments }, accepting both the
  // new Multi-Script schema ("command"/"params") and the legacy/function-calling
  // schema ("tool"/"arguments"/"name"/"args"). Returns null if not a valid call.
  function normalizeCall(o) {
    if (!o || typeof o !== "object") return null;
    const name = o.command != null ? o.command : (o.tool != null ? o.tool : o.name);
    let args = o.params != null ? o.params : (o.arguments != null ? o.arguments : o.args);
    if (typeof name !== "string" || !name) return null;
    if (typeof args === "string" && args.trim()) {
      // Models sometimes double-encode: "params": "{\"path\": ...}".
      try { const inner = parseLoose(args); if (inner && typeof inner === "object") args = inner; } catch {}
    }
    if (!args || typeof args !== "object" || Array.isArray(args)) args = {};
    return { tool: name, arguments: args };
  }

  // String-aware matching-brace finder: index of the "}" that closes the "{" at
  // `start`, SKIPPING braces inside JSON string literals (escaped quotes handled).
  // A naive depth counter miscounts the braces embedded in code passed as a string
  // value (e.g. multi_edit's edits / a Lua snippet), grabs the wrong end, and makes
  // JSON.parse fail - which silently dropped the command, so the tool never ran and
  // the turn was treated as a plain-text answer. Returns -1 if unbalanced.
  function matchBrace(text, start) {
    let depth = 0, inStr = false, esc = false;
    for (let i = start; i < text.length; i++) {
      const c = text[i];
      if (inStr) {
        if (esc) esc = false;
        else if (c === "\\") esc = true;
        else if (c === '"') inStr = false;
      } else if (c === '"') inStr = true;
      else if (c === "{") depth++;
      else if (c === "}") { if (--depth === 0) return i; }
    }
    return -1;
  }

  // JSON.parse with a fallback for RAW control characters inside string
  // literals (tab/newline/CR). Models sometimes emit a literal TAB instead of
  // \t inside a command's string value (seen live on Gemini in a big
  // multi_edit); strict JSON rejects it, the parse failed silently and the
  // command was never executed. The fallback walks the text string-aware and
  // escapes those characters ONLY inside string literals, then re-parses.
  function parseLoose(raw) {
    // Tier 0: strict. Tier 1: raw control characters inside strings (the original
    // fix). Tier 2: the common ways a chat model breaks JSON - smart quotes,
    // single quotes, comments, trailing commas, unquoted keys, Python literals,
    // invalid escapes (`\d`, `\'`). Tier 3: additionally guess which inner
    // double quotes were meant literally. Every tier only runs when the one
    // before it threw, so a well-formed command is never touched.
    try { return JSON.parse(raw); } catch (e0) {
      let last = e0;
      for (const mode of [0, 1, 2]) {
        try { return JSON.parse(repairJsonText(raw, mode)); } catch (e) { last = e; }
      }
      throw last;
    }
  }

  // Repair JSON-ish text into strict JSON. mode 0 = control chars only,
  // 1 = lenient syntax, 2 = lenient syntax + inner-quote guessing.
  function repairJsonText(raw, mode) {
    const n = raw.length;
    const lenient = mode >= 1, guess = mode >= 2;
    const OPEN_DQ = new Set(['"', "\u201c", "\u201d", "\u201e", "\u00ab", "\u00bb"]);
    const CLOSE_DQ = new Set(['"', "\u201d", "\u201c", "\u201e", "\u00bb", "\u00ab"]);
    const nextSig = (i) => { while (i < n && /\s/.test(raw[i])) i++; return i < n ? raw[i] : ""; };
    let out = "";
    let i = 0;
    while (i < n) {
      const c = raw[i];
      // ---- comments (outside strings only) ----
      if (lenient && c === "/" && raw[i + 1] === "/") { while (i < n && raw[i] !== "\n") i++; continue; }
      if (lenient && c === "/" && raw[i + 1] === "*") { const e = raw.indexOf("*/", i + 2); i = e === -1 ? n : e + 2; continue; }
      // ---- strings ----
      const isDq = c === '"' || (lenient && OPEN_DQ.has(c));
      const isSq = lenient && c === "'";
      if (isDq || isSq) {
        const quote = c;
        out += '"';
        i++;
        while (i < n) {
          const d = raw[i];
          if (d === "\\") {
            const nx = raw[i + 1];
            if (nx === undefined) { out += "\\\\"; i++; continue; }
            if ('"\\/bfnrt'.includes(nx)) { out += d + nx; i += 2; continue; }
            if (nx === "u" && /^[0-9a-fA-F]{4}$/.test(raw.slice(i + 2, i + 6))) { out += raw.slice(i, i + 6); i += 6; continue; }
            if (nx === "'") { out += "'"; i += 2; continue; }
            // Not a JSON escape (e.g. Lua/regex "\d", "\.", a Windows path): keep the backslash literally.
            if (lenient) { out += "\\\\"; i++; continue; }
            out += d + nx; i += 2; continue;
          }
          const closes = isDq ? (d === '"' || (lenient && CLOSE_DQ.has(d))) : d === "'";
          if (closes) {
            if (guess && isDq) {
              // A real closing quote is followed by , } ] : or end of input.
              const nx = nextSig(i + 1);
              if (nx && !",}]:".includes(nx)) { out += '\\"'; i++; continue; }
            }
            if (isSq && lenient) {
              const nx = nextSig(i + 1);
              if (nx && !",}]:".includes(nx)) { out += "'"; i++; continue; }
            }
            out += '"';
            i++;
            break;
          }
          if (d === '"') { out += '\\"'; i++; continue; }   // a bare " inside a single-quoted string
          if (d === "\t") { out += "\\t"; i++; continue; }
          if (d === "\n") { out += "\\n"; i++; continue; }
          if (d === "\r") { out += "\\r"; i++; continue; }
          if (d < " ") { out += "\\u" + d.charCodeAt(0).toString(16).padStart(4, "0"); i++; continue; }
          out += d;
          i++;
        }
        continue;
      }
      if (lenient) {
        // trailing comma: ,  followed by } or ]
        if (c === ",") {
          const nx = nextSig(i + 1);
          if (nx === "}" || nx === "]") { i++; continue; }
        }
        // bare words: unquoted keys and Python/JS literals
        if (/[A-Za-z_$]/.test(c)) {
          let j = i;
          while (j < n && /[A-Za-z0-9_$]/.test(raw[j])) j++;
          const word = raw.slice(i, j);
          const nx = nextSig(j);
          if (nx === ":") { out += JSON.stringify(word); i = j; continue; }
          const lit = { True: "true", False: "false", None: "null", undefined: "null", NaN: "null", Infinity: "null", true: "true", false: "false", null: "null" }[word];
          if (lit !== undefined) { out += lit; i = j; continue; }
          out += word; i = j; continue;
        }
      }
      out += c;
      i++;
    }
    return out;
  }

  function extractJson(raw) {
    raw = raw.trim().replace(/^(?:json|JSON)\s*/, "");
    raw = raw.replace(/^```(?:json)?\s*/i, "").replace(/```\s*$/, "").trim();
    const s = raw.indexOf("{");
    if (s === -1) return null;
    const e = matchBrace(raw, s);            // string-aware: not the last "}" in code
    if (e === -1) return null;
    try {
      return parseLoose(raw.slice(s, e + 1));
    } catch {
      return null;
    }
  }

  function extractToolAnywhere(text) {
    for (const key of ['"command"', '"tool"']) {
      let pos = 0;
      while (true) {
        const s = text.indexOf(key, pos);
        if (s === -1) break;
        const start = text.lastIndexOf("{", s);
        if (start === -1) { pos = s + 1; continue; }
        const end = matchBrace(text, start); // string-aware brace matching
        if (end === -1) { pos = s + 1; continue; }
        try {
          const call = normalizeCall(parseLoose(text.slice(start, end + 1)));
          if (call) return call;
        } catch {}
        pos = s + 1;
      }
    }
    return null;
  }

  function decodeMarkupText(value) {
    return String(value || "")
      .replace(/&quot;/gi, '"').replace(/&#39;|&apos;/gi, "'")
      .replace(/&lt;/gi, "<").replace(/&gt;/gi, ">").replace(/&amp;/gi, "&");
  }

  // Compatibility only: some model hosts may ignore the JSON-only instruction
  // and emit their private invoke/parameter tags. Normalize that accidental
  // transport into Multi-Script's ordinary {tool, arguments} call internally;
  // the tags are never advertised to a model and never sent back to it.
  function parseNativeToolMarkup(text) {
    if (!DSML_RE.test(text || "")) return [];
    // DeepSeek writes the tags in several shapes, depending on model build and on how the
    // site renders them (all seen / documented):
    //   <|DSML|>invoke name="x">      (bars, ">", tag)      - older tool_calls form
    //   <｜DSML｜invoke name="x">       (full-width bars, NO ">" before the tag)
    //   <|DSML|invoke name="x">       (ASCII bars, no ">")
    //   < | DSML | invoke name="x">   (spaced, as some renderers print it)
    // Fold every one of them to <native:tag ...> first. The ">" after the bars is optional.
    const canonical = String(text).replace(
      /<\s*(\/?)\s*[|｜][\s|｜]*DSML[\s|｜]*[|｜]\s*>?\s*([A-Za-z_]+)/gi,
      (_m, close, tag) => `<${close ? "/" : ""}native:${tag.toLowerCase()}`
    );
    const calls = [];
    // An invoke ends at its closer, at the next invoke, at the closing function_calls /
    // tool_calls tag, or at the end of the text (the model stopped right after the last
    // </parameter>). A parameter that never closed is NOT accepted below: that is a cut-off
    // value and running it would act on half a payload.
    const invokeRe = /<native:invoke\b([^>]*)>([\s\S]*?)(?=<\/native:invoke\s*>|<native:invoke\b|<\/native:(?:function_calls|tool_calls)|$)/gi;
    let inv;
    while ((inv = invokeRe.exec(canonical))) {
      const nm = /\bname\s*=\s*["']([^"']+)["']/i.exec(inv[1]);
      if (!nm || !nm[1].trim()) continue;
      const body = inv[2];
      const opens = (body.match(/<native:parameter\b/gi) || []).length;
      const closes = (body.match(/<\/native:parameter\s*>/gi) || []).length;
      if (opens !== closes) continue;      // cut off inside a parameter
      const args = {};
      const paramRe = /<native:parameter\b([^>]*)>([\s\S]*?)<\/native:parameter\s*>/gi;
      let pm;
      while ((pm = paramRe.exec(body))) {
        const key = /\bname\s*=\s*["']([^"']+)["']/i.exec(pm[1]);
        if (!key) continue;
        const raw = decodeMarkupText(pm[2].trim());
        const forceString = /\bstring\s*=\s*["']true["']/i.test(pm[1]);
        let value = raw;
        if (!forceString) {
          if (/^(?:true|false)$/i.test(raw)) value = raw.toLowerCase() === "true";
          else if (/^-?(?:\d+\.?\d*|\.\d+)$/.test(raw)) value = Number(raw);
          else if (/^[\[{]/.test(raw)) { try { value = JSON.parse(raw); } catch {} }
        }
        args[key[1]] = value;
      }
      calls.push(cleanLuaCall({ tool: nm[1].trim(), arguments: args }));
    }
    return calls;
  }

  // The tool an unreadable / half-written DSML block names, or "" (the chip then says
  // "command" and the feedback cannot name the tool).
  function nativeToolName(text) {
    const m = /invoke\b[^>]*?\bname\s*=\s*["']([^"']+)["']/i.exec(String(text || ""));
    return m && m[1].trim() ? m[1].trim() : "";
  }

  function parseToolCalls(r) {
    r = foldTypography(r);
    // Lowercase for case-insensitive end-marker search. Models write
    // ###end_mcp_tool### (underscore) or ###end-mcp_tool### (dash).
    const rLow = r.toLowerCase();
    const findEndM = (from) => {
      const a = rLow.indexOf("###end_mcp_tool###", from);
      const b = rLow.indexOf("###end-mcp_tool###", from);
      if (a === -1 && b === -1) return -1;
      if (a === -1) return b;
      if (b === -1) return a;
      return Math.min(a, b);
    };
    const out = [];
    let from = 0;
    while (true) {
      const sm = r.indexOf(START_M, from);
      if (sm === -1) break;
      const em = findEndM(sm);
      if (em === -1) break;
      const body = r.slice(sm + START_M.length, em);
      const { pos: ls, len: luaLen, dm } = findLuaStart(body);
      const le = findLuaEnd(body, ls === -1 ? 0 : ls + luaLen);
      if (ls !== -1 && le !== -1 && le > ls) {
        out.push({ tool: "execute_luau", arguments: { code: stripCodeChrome(body.slice(ls + luaLen, le).trim()), datamodel_type: dm } });
        from = em + END_M.length;
        continue;
      }
      for (const sub of body.split(START_M)) {
        const cleaned = sub.trim().replace(/^(?:json|JSON|Copy|copy)\s*/i, "").trim();
        if (!cleaned) continue;
        const p = normalizeCall(extractJson(cleaned));
        if (p) out.push(p);
      }
      from = em + END_M.length;
    }
    if (out.length === 0) out.push(...parseNativeToolMarkup(r));
    // Prefer a JSON command envelope when one is present: a model may wrap
    // execute_luau as {"command":"execute_luau","params":{"code":"###LUA###…"}},
    // and the bare-marker fallback below would slice the still-ESCAPED JSON
    // source (literal \n, \") instead of the decoded code. extractToolAnywhere
    // JSON-decodes it; cleanLuaCall (applied at the end) then strips the markers.
    if (out.length === 0) {
      const f = extractToolAnywhere(r);
      if (f) out.push(f);
    }
    // Bare ###LUA### … ###END_LUA### block with no JSON envelope at all.
    if (out.length === 0) {
      const { pos: ls, len: luaLen, dm } = findLuaStart(r);
      const le = findLuaEnd(r, ls === -1 ? 0 : ls + luaLen);
      if (ls !== -1 && le !== -1 && le > ls) {
        out.push({ tool: "execute_luau", arguments: { code: stripCodeChrome(r.slice(ls + luaLen, le).trim()), datamodel_type: dm } });
      }
    }
    return out.map(cleanLuaCall);
  }

  // Some models (seen live on GLM) wrap execute_luau in the JSON envelope AND
  // keep the ###LUA### / ###END_LUA### markers INSIDE the code string, e.g.
  //   {"command":"execute_luau","params":{"code":"###LUA###\n<lua>\n###END_LUA###"}}
  // Once JSON-decoded the code still starts with the literal markers, which the
  // MCP rejects ("Failed to parse command code"). Strip a leading start marker
  // and a trailing end marker from execute_luau's code, and adopt the marker's
  // datamodel when none was given. No-op for a clean code string.
  function cleanLuaCall(call) {
    if (!call || call.tool !== "execute_luau") return call;
    const code = call.arguments && call.arguments.code;
    if (typeof code !== "string") return call;
    const s = findLuaStart(code);
    if (s.pos === -1) return call;
    const e = findLuaEnd(code, s.pos + s.len);
    call.arguments.code = code.slice(s.pos + s.len, e === -1 ? code.length : e).trim();
    if (!call.arguments.datamodel_type) call.arguments.datamodel_type = s.dm;
    return call;
  }

  // Last-resort salvage of a CUT-OFF JSON command: the model hit its output
  // limit with the whole payload complete but the trailing closers missing
  // (seen live on Qwen: a big multi_edit missing exactly ONE final "}").
  // Strictly conservative - we only auto-close when it is provably just the
  // closing sequence that was lost, never when actual content was amputated:
  //  - the scan must NOT end inside a string literal (a value cut mid-string
  //    means real content is missing → keep the parse_error);
  //  - the last non-whitespace char must terminate a complete JSON value
  //    (`"`, `}`, `]`, digit, or the tail of true/false/null);
  //  - at most MAX_SALVAGE_CLOSERS closers may be appended. 2 covers the
  //    root-brace and params-brace cases; a deeper deficit usually means the
  //    cut fell between items (e.g. mid-edits-array), where running a partial
  //    command would be dangerous - the retry feedback stays the right call.
  // Callers must only invoke this once generation has ENDED (the watcher's
  // parse_error branch), never on a still-streaming reply.
  const MAX_SALVAGE_CLOSERS = 2;
  function salvageCutOff(text) {
    for (const key of ['"command"', '"tool"']) {
      const k = text.indexOf(key);
      if (k === -1) continue;
      const start = text.lastIndexOf("{", k);
      if (start === -1) continue;
      if (matchBrace(text, start) !== -1) continue; // closed → not our case
      // String-aware bracket stack from the opener to the end of the text.
      const stack = [];
      let inStr = false, esc = false;
      for (let i = start; i < text.length; i++) {
        const c = text[i];
        if (inStr) {
          if (esc) esc = false;
          else if (c === "\\") esc = true;
          else if (c === '"') inStr = false;
        } else if (c === '"') inStr = true;
        else if (c === "{") stack.push("}");
        else if (c === "[") stack.push("]");
        else if (c === "}" || c === "]") {
          if (stack.pop() !== c) return null; // mismatched nesting → hopeless
        }
      }
      if (inStr) return null;                       // cut mid-string value
      if (!stack.length || stack.length > MAX_SALVAGE_CLOSERS) return null;
      const body = text.slice(start).trimEnd();
      if (!/["}\]0-9]$|(?:true|false|null)$/.test(body)) return null; // value incomplete
      try {
        const call = normalizeCall(parseLoose(body + stack.reverse().join("")));
        if (call) return cleanLuaCall(call);
      } catch {}
      return null;
    }
    return null;
  }

  function toolNameFromText(txt) {
    // Match the name even BEFORE its closing quote (`[^"]*`), so the chip shows
    // the real command name AS IT IS TYPED instead of a generic "command"
    // placeholder until the JSON closes. A still-empty value falls through.
    // Trim: while the value is still streaming it can be whitespace-only (e.g.
    // Kimi renders `"tool": "    "` for a beat), which would otherwise show a
    // blank chip label until the loop repaints it. A whitespace value falls
    // through to the placeholder below instead.
    if (DSML_RE.test(txt)) { const dn = nativeToolName(txt); if (dn) return dn; }
    const m = txt.match(/"(?:command|tool)"\s*:\s*"([^"]*)/);
    if (m && m[1].trim()) return m[1].trim();
    if (txt.includes("execute_luau") || LUA_START_RE.test(txt)) return "execute_luau";
    return "command";
  }

  // A turn the EXTENSION injected (always sent as a user turn): a tool result, an
  // ERROR, or a "(System note: …)" control message. Matched ONLY by the fixed
  // shapes we emit - never by command-like keywords, since a parse-error note
  // quotes a {"command": …} example that must NOT be read as a real command.
  function isInjectedFeedback(txt) {
    return /^\s*Output of (?:'[^']+'|[A-Za-z_][\w.]*)\s*:/.test(txt) ||
           /^\s*ERROR\b/.test(txt) ||
           /^\s*\(System note:/.test(txt);
  }

  // The assistant emitted a Multi-Script command (JSON or a ###LUA### block), or a
  // command-turn ATTEMPT the camouflage sweep should still mask. DSML counts:
  // the turn IS the model calling a tool, just in the wrong dialect, so it gets a
  // chip like any other command turn instead of dumping raw markup at the user
  // (reported live 2026-08-22 - the error fired correctly but the tags stayed on
  // screen). Note this is deliberately NOT mirrored in hasToolSignature: that
  // one gates the parse/execute path, and DSML must keep falling through to the
  // classify ladder so it fires the "dsml" parse_error rather than being handed
  // to parseToolCalls, which cannot read it.
  function hasCommandShape(txt) {
    return txt.includes(START_M) ||
           LUA_START_RE.test(txt) ||
           DSML_RE.test(txt) ||
           CMD_KEY_RE.test(txt); // command/tool with OR without params (e.g. list_commands)
  }

  // ── diagnose(): WHY a command-shaped reply could not be parsed ─────────────
  // The old feedback told the model "not one complete plain-text JSON object" no
  // matter what went wrong, so a reply that was simply CUT OFF (site output cap,
  // generation halted) looked identical to bad escaping and the model insisted
  // its JSON was valid. This scans the reply once and reports facts the feedback
  // (and the log) can state truthfully: how long it was, whether it ended inside a
  // string / with unclosed braces, smart quotes, raw newlines inside strings, text
  // after the object, and the first spot a strict parse chokes on.
  function diagnose(raw) {
    const text = String(raw == null ? "" : raw);
    const out = { length: text.length, start: -1, depth: 0, endedInString: false, balancedAt: -1, trailing: "",
      smartQuotes: 0, rawNewlinesInStrings: 0, badEscapes: 0, fenced: /```/.test(text), tail: text.slice(-100),
      strictError: "", strictContext: "", kind: "unknown" };
    let s = text.search(/\{\s*["\u201c]\s*(?:command|tool)\s*["\u201d]/);
    if (s === -1) s = text.indexOf("{");
    out.start = s;
    if (s === -1) { out.kind = "no-object"; return out; }
    let depth = 0, inStr = false, esc = false;
    for (let i = s; i < text.length; i++) {
      const c = text[i];
      if (c === "\u201c" || c === "\u201d") out.smartQuotes++;
      if (inStr) {
        if (esc) { esc = false; if (!'"\\/bfnrtu'.includes(c)) out.badEscapes++; continue; }
        if (c === "\\") { esc = true; continue; }
        if (c === '"') { inStr = false; continue; }
        if (c === "\n" || c === "\r") out.rawNewlinesInStrings++;
        continue;
      }
      if (c === '"') { inStr = true; continue; }
      if (c === "{" || c === "[") depth++;
      else if (c === "}" || c === "]") { depth--; if (depth === 0) { out.balancedAt = i; break; } }
    }
    out.depth = depth; out.endedInString = inStr;
    if (out.balancedAt !== -1) {
      out.trailing = text.slice(out.balancedAt + 1).trim().slice(0, 80);
      const body = text.slice(s, out.balancedAt + 1);
      try { JSON.parse(body); out.kind = out.trailing ? "trailing-text" : "valid"; }
      catch (e) {
        const msg = String(e && e.message || e);
        out.strictError = msg.slice(0, 140);
        const m = /position (\d+)/.exec(msg) || /column (\d+)/.exec(msg);
        if (m) {
          const at = +m[1]; out.strictContext = body.slice(Math.max(0, at - 40), at + 40).replace(/\s+/g, " ");
        }
        out.kind = out.smartQuotes ? "smart-quotes" : out.rawNewlinesInStrings ? "raw-newlines" : out.badEscapes ? "bad-escape" : "bad-json";
      }
    } else {
      out.kind = out.endedInString ? "cut-off-in-string" : "cut-off";
    }
    return out;
  }

  return {
    diagnose,
    START_M, END_M, LUA_START_RE, LUA_END_RE, CMD_KEY_RE, DSML_RE,
    findLuaStart, findLuaEnd, matchBrace, parseLoose, repairJsonText, extractJson, normalizeCall, parseNativeToolMarkup, nativeToolName,
    hasToolSignature, hasOpenToolBlock, parseToolCalls, salvageCutOff, toolNameFromText,
    isInjectedFeedback, hasCommandShape,
  };
})();
