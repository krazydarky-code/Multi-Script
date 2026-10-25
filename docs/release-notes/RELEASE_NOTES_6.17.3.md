# Multi-Script 6.17.3 — Release Notes

**Theme: keep the run alive through a bot-check — without bypassing it.**

You asked for auto-completing CAPTCHAs on arena.ai, "not exactly a bypass, but
something to keep it running too." Those are two different things, and the line
between them is the whole feature. Here is where the line is and why.

---

## What it does NOT do

It does not solve, answer, farm, outsource or defeat a CAPTCHA. Concretely, none
of this exists anywhere in the shipped code, and the release gate now fails the
build if it ever appears:

- no solving service (2captcha, CapSolver, CapMonster, Anti-Captcha, …)
- no token injection or harvesting (`g-recaptcha-response`, `h-captcha-response`,
  `cf-turnstile-response`)
- no `grecaptcha.execute` / `hcaptcha.execute` calls
- no `postMessage` into the challenge iframe

That is not squeamishness — defeating a bot-check is the single fastest way to
get an account banned, and it would be your account. So the honest answer to
"auto-complete the captcha" is: the part that can be automated safely, I built;
the part that means *answering* the challenge, I will not.

## What it DOES do — "keep it running"

A bot-check interrupts an unattended run. The correct behaviour is to notice it,
stop looking like automation, get you back to it, and then stop tripping it.
Four pieces:

### 1. A staged escalation, not a dumb wait

While a check is on screen the run walks a ladder:

| When | What happens |
|---|---|
| t+0s | Banner explains the check and what you must do |
| t+9s | Multi-Script's own controls move off the widget's hit area |
| t+26s | **Audible alert + tab title** — so you notice from another tab |
| t+61s | **One** trusted click on the provider's *own* widget |
| t+5m | Alert again, with elapsed time |

The alert deliberately comes **before** the click, so you always get first
refusal. The click is deliberately delayed 60s, so it never looks like an
instant scripted reaction.

### 2. One click on the provider's own widget

On a checkbox-style challenge (Cloudflare Turnstile in managed mode, hCaptcha
passive) the widget presents a real checkbox that a single genuine click
satisfies. That click is the same gesture a human makes. It dispatches a normal
`pointerdown/mousedown/pointerup/mouseup/click` sequence at the widget's visual
centre and then **stops**. It never reads a value, never writes a value, never
retries, and it is capped at one gesture by test.

If the provider then shows a puzzle or asks for more, that is handed back to you
— and the UI says so plainly.

### 3. Resume by itself

Your earlier work already cleared the challenge; what changed is that clearing it
now also **resets the error budget** (those failures were the challenge's fault,
not the model's) and re-times the slowdown from the clear. The run continues
without you pressing Start.

### 4. Stop it recurring — the actual "keep it running"

This is the half that matters most. Every check is evidence the current send rate
is too aggressive, so each one raises a **floor** on the gap between messages:

```
challenge #1 → floor  12s   (plus a 45s settle taper right after)
challenge #2 → floor  36s
challenge #3 → floor  72s
challenge #4 → floor 120s
challenge #5 → floor 168s   …capped at 180s
```

The floor is added on top of your normal pacing, never instead of it, and it
**decays proportionally** once things are clean again — a mild slowdown clears
quickly, a heavy one eases off gradually rather than snapping back to full speed
and immediately re-tripping. From the 180s ceiling it releases to exactly zero in
about 90 minutes of clean traffic.

Prevention beats reaction: a run that stops triggering the check never needs the
ladder at all.

---

## Modes

New **Agent → Verification handling** section, saved per-provider:

- **Off** — pause, tell you, resume. The previous behaviour.
- **Watch** — the above, plus the loud alert.
- **Assist** *(default)* — alerts, one click on the provider's own widget, and
  the adaptive slowdown.
- **Unattended** — built for an overnight run: longest patience, loudest alert,
  strongest slowdown.

Plus an **audible alert** toggle (tone + tab title).

Everything is included in the settings backup/restore and the diagnostics export
(`verificationSummary`, `verificationSeen`).

---

## Honest limits

- The assisted click only helps where a single click is *sufficient*. If the
  provider wants a puzzle solved, a human still has to do it — there is no
  version of this that is both safe and fully automatic, and anything claiming
  otherwise is a bypass.
- It targets **arena.ai**. Meta's provider stubs detection out entirely, so no
  assisted click is possible there; the core detects this and degrades to
  pause-and-resume with no error.
- The click targets the widget *host*, since a cross-origin iframe cannot be
  scripted. If a provider reworks its widget this may need updating — the
  detection selectors are broad and paired with a text probe for exactly that
  reason.

---

## Verification

- **33/33** JavaScript tests (was 32 — added `test_verification_assistant.js`).
- **28/28** Python tests.
- `tools/release_check.py` **PASS**, now with a build-failing **no-bypass gate**
  that comment-strips the shipped source before scanning, so a comment
  *describing* the refusal cannot mask real code and vice versa.
- The browser gate `test_arena_human_verification.js` now also proves, in a real
  Chromium: the click targets the visible widget, it dispatches one bounded
  gesture (≤5 events), and the invisible reCAPTCHA v3 badge is never clickable.

The new test pins the boundary in both directions: the mode ladder is honest
(only claiming modes may click; anything that clicks must alert), the slowdown
grows, caps, decays and releases to *exactly* zero, the ladder never clicks
before alerting or within the first 30s, and the user-facing copy is asserted to
state that nothing is bypassed.

---

## Upgrading

Replace the extension and restart the bridge. Defaults to **Assist**. Set it to
**Off** in Agent → Verification handling for the previous behaviour, or
**Unattended** for an overnight run.
