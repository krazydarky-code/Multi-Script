# Multi-Script 6.16.0 — Pacing, Recovery, One-Shot and JSON Discipline

This release is about making the agent survivable when you are NOT watching it.
It adds a real reply-pacing engine, a bounded error-recovery policy, an
unattended one-shot mode, a much stronger JSON-only transport contract, and
substantially better Arena and Notion behaviour — with the Godot path as the
primary non-Roblox focus.

## Reply pacing (anti-flag)

The loop used to send turns back-to-back with a fixed ~200 ms settle. That
machine-perfect cadence is exactly what behavioural risk-scoring reads as
automation, alongside the necessarily-synthetic input events. `core/pacing.js`
now owns the rhythm:

- **Off** — send immediately (the original behaviour; a real switch, not a stub).
- **Brisk** — 0.4–1.4 s of jitter, still fast, less robotic.
- **Human-like** (default) — 1.5–4.5 s randomised band, a 5–15 s longer break every 8th send, 8 s cooldown after any error.
- **Cautious** — 3–9 s band, a 10–30 s break every 5th send, 20 s cooldown, optional typing simulation at ~14 chars/s.
- **Custom** — your own numbers, clamped to sane ceilings.

The gap is measured **since the last send**, so a slow reply or an image upload
is never double-taxed. Any error or throttle arms a cooldown that a retry cannot
shorten, which is the actual defence against a retry storm deepening a rate
limit. Pacing only changes **when** a turn is sent — never what is sent — so it
cannot lower correctness. The bar shows `Pacing · next turn in ~Ns` while it
waits, so a deliberate gap never looks like a hang.

Per-provider overrides let you mark one site (e.g. Arena) as Cautious while
everything else stays Off.

## Error recovery (unattended survivability)

`core/resilience.js` decides what happens when a turn comes back empty, times
out, or is not one valid command:

- **Off** — a failure ends the run, as before.
- **Standard** — recovers from the common one-off hiccup (2 retries per failure, 3 in a row).
- **Persistent** — keeps a long run alive: 6 retries with escalating backoff, up to 8 consecutive failures, and wider patience windows for slow replies, warm-ups, reasoning phases and still-streaming command blocks.

Recovery is bounded on purpose: a per-failure budget *and* a consecutive-failure
cap, so a genuinely broken session stops honestly instead of burning quota. A
retry only ever **re-asks** — it never fabricates a result, and every nudge says
explicitly that nothing was run. A command that parses successfully resets the
streak.

## One-shot / unattended mode

Paste a design specification, walk away. One-shot mode injects an autonomy block
that forbids questions, forbids dead turns (a turn that announces a command
without writing it), requires the whole specification to be driven to
completion, requires silent self-recovery from hiccups, and restricts stopping to
choices that are destructive, paid, credentialed or genuinely contradictory.
It finishes with one short evidence-based completion report.

Selecting One-shot also raises the two floors it depends on: **Persistent**
recovery and **Human-like** pacing.

## Human verification (bot-checks)

Arena can answer an automated cadence with a Cloudflare Turnstile / hCaptcha /
reCAPTCHA / Arkose / DataDome / PerimeterX / GeeTest challenge, or a plain
"verify you are human" interstitial. Detection is now much broader — known
challenge widgets **plus** an independent text probe, each requiring real
visibility, real size and a chat-free host element, so Arena's always-present
hidden reCAPTCHA v3 badge can never false-positive.

**Multi-Script does not solve, token-inject, outsource or otherwise bypass a
challenge.** Instead it now behaves like a well-mannered human: it notices the
challenge, stops typing into the composer, gets its own bar out of the way, tells
you exactly what to do, and then **resumes by itself** the moment it clears — at
startup, mid-loop, and mid-send. Previously a bot-check killed the run.

## Notion reliability

- The stop/generation affordance is now matched across several wordings and a `data-testid` probe, so a missed stop button can no longer make the loop think a still-streaming turn is finished.
- `typeAndSend` tries button click, Enter, and form submit in turn, verifying the composer actually cleared between attempts, and restores the text if the site wiped it without sending.
- A mid-render read is now reported as unsettled so the core waits instead of firing a false "malformed command" verdict.

## JSON-only transport discipline

Every engine — Roblox first, Godot alongside — is now governed by an explicit
**JSON-ONLY CONTRACT** in the system prompt and restated by the periodic
mid-session reminder: one plain-text object, `{"command":…,"params":{…}}`, no
fences, no XML/DSML/function-call markup, no wrapper keys, no nesting, one
command per reply, with the exact parameter shapes for `execute_luau` and
`multi_edit` spelled out. The core additionally unwraps a double-wrapped
envelope (depth-bounded) instead of refusing a call the model obviously meant.

## Godot

The Godot rule is now concrete: confirm the server with `get_godot_version`, then
`get_project_info` for the real project path, use that **exact absolute path** for
every later call, inspect before writing, run/read `get_debug_output`/stop
cleanly, and remember Godot paths are case-sensitive on Linux and macOS.

## Verification

Four new pure-logic gates run in CI without a browser:
`test_pacing_engine.js` (off switch, band bounds, long-pause cadence, error
cooldown, per-provider overrides, sanitisation, determinism under a seeded RNG),
`test_error_recovery.js` (every branch of the recovery policy),
`test_one_shot_autonomy.js` (prompt rules + core wiring + manifest load order),
and `test_roblox_json_contract.js` (prompt, reminder, seven live Roblox/Godot
envelopes, nested edits arrays, double-envelope unwrap).

The CI workflow also no longer references three test files that are absent from
this build (`test_quality_prompt.js`, `test_quality_amplifier.py`,
`test_studio_quality_autopilot.py`), which previously made the pipeline red on
every push.

## Transient site outages no longer end a run

A site answering "server is busy / please try again" is not the model's answer. That
used to fall through to a normal terminal turn and stop the loop — the commonest real
failure on DeepSeek at peak hours. It is now classified as `busy` and given exactly
**one** bounded retry: enough to ride out a hiccup, capped so a model answer that
merely tells the *user* to try again can never loop. The gates are deliberately tight
(short reply, no command shape, not our own feedback, the provider's own site-error
phrasing).

## Per-site pacing, and an in-menu pacing check

- **Scope toggle**: pacing can now be applied to *this site only*, which makes the
  engine's per-provider override reachable — "slow down on the site that flags me,
  keep everything else instant". The status line says which it is.
- **Test pacing** button: runs the same engine the loop uses over a simulated session
  and reports the real numbers (mean/min/max gap, longer breaks, the cost of a
  ~60-send run, the error cooldown, and the active recovery budget) in the panel — so
  "is pacing actually doing something on my machine" is answerable without reading code.

## Godot launcher hardening

`runtime/launch_godot_mcp.py` now:

- **auto-detects the Godot editor** (`ZS_GODOT_PATH` / `GODOT_PATH` / `GODOT4_PATH` /
  `GODOT_BIN`, then the usual Windows / macOS / Linux install locations, then PATH) and
  sets `GODOT_PATH` for the server. Previously the server started fine and then failed
  every project call with an opaque error;
- reports clearly on **stderr** what it found, or exactly what to set when it found
  nothing — and never writes to **stdout**, which is the MCP JSON-RPC channel (a stray
  line there corrupts the handshake and makes the server look dead);
- forwards **Ctrl+C** to the child instead of orphaning it, so a bridge restart cannot
  leave the old server holding the project folder;
- keeps the version pin, `ZS_GODOT_MCP_VERSION`, `ZS_NPX_PATH` and argv passthrough, and
  now passes the child's **exit code** through.

## Arena detection: two real bugs found by the new test

Writing a dependency-free headless test for the detection logic (see below) surfaced:

- the challenge **kind** was derived only from an iframe `src`, so an inline Turnstile
  (`div.cf-turnstile` with no iframe yet) reported a generic kind instead of
  "cloudflare turnstile" in the user-facing hint. It is now derived from src, class,
  id, `data-testid` and `data-sitekey` — via `getAttribute("class")` rather than
  `.className`, because on SVG elements `className` is an object, not a string;
- **PerimeterX/HUMAN** challenges are served from `px-cdn.net` and `human-challenge`
  hosts, which the selector list missed entirely.

## The whole test suite is now actually runnable

The browser gates hardcoded `executablePath: '/usr/local/bin/chromium'`, a path that
exists on one custom CI image — so on plain `ubuntu-latest`, on macOS and on Windows
they threw for a reason unrelated to the product. A new `tests/playwright-env.js`
resolves a browser from `CHROMIUM_PATH` → common system locations → Playwright's
bundled Chromium, and **skips cleanly** (exit 0, loud message) when none is available,
so a missing browser can never masquerade as a product failure. CI now installs
Playwright instead of referencing it without installing it.

Result: all six browser gates pass in a real Chromium — including the Arena
human-verification gate against a real DOM, and the Notion DOM gate exercising the new
three-strategy send.

## Verification

- `python tools/release_check.py` → PASS (800 skills, 50 JavaScript files).
- All six browser gates pass in real Chromium (system Chrome, headless).
- New browser-free gates: `test_arena_verification_detection.js` (13 challenge widgets,
  4 interstitial wordings, 4 false-positive guards, no bypass implementation) and
  `test_godot_launcher.py` (version pin, `.cmd` wrapping, `ZS_NPX_PATH`, per-platform
  Godot detection, clean failure without npx, exit-code/argv passthrough, **stdout kept
  empty**).
- The remaining Python gates pass unchanged (`test_all_skills_and_tools.py` is simply
  slow at ~2m8s).

## Honest limitations

- Pacing and recovery change timing and retry behaviour. They do not make an
  automated session indistinguishable from a human, and they do not guarantee a
  site will never rate-limit or challenge it. They remove the *most obvious*
  automation signature and prevent retry storms.
- Recovery re-asks the model. If a site is genuinely down, the run still ends —
  honestly, and after a bounded number of attempts.
- A bot-check still requires **you** to clear it. That is deliberate.
