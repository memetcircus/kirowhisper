# KiroWhisper — Use Cases

> This document defines KiroWhisper's usage scenarios. Requirements (user story +
> acceptance criteria) derive from here. Each use case lists: actor, trigger,
> flow, **spike-reality** (what the live test proved), and **priority**.

---

## 0. Identity: what KiroWhisper is (one sentence)

A **colleague that lets you oversee the autonomous Kiro Crew by voice, without
looking at a screen** — it filters the noise for you, surfaces only the real
decision, and handles the rest safely.

**A colleague, not a tool.** Not a command-obeying assistant; a teammate working
in the next room that consults you when needed and proceeds safely when it doesn't.

## Persona
- **Deniz** — a blind, home-office developer. Doesn't sit at the desk continuously.
  Uses a screen reader, but stepping through long agent output/approvals by voice
  one by one is torture. The core heart.
- **Curb-cut expansion** — anyone away from the screen (breakfast, kitchen, hands/eyes busy).

## Value hierarchy (fixed)
1. TECHNICAL: Ambient Awareness (smart filter + risk classification) + safe approval.
2. EXPERIENCE: the two-way "live colleague" feel, eyes-free.
3. DIGNITY: genuine accessibility for a blind developer (curb-cut).

## Competitive difference (kept clear)
"Voice coding" is NOW A COMMODITY (ChatGPT Voice->Codex, Google Antigravity). Our
difference is NOT writing code by voice. Our difference is:
(a) accessibility-first (a blind developer's real pain — confirmed by MS Research + arXiv),
(b) eyes-free/remote AUTONOMOUS OVERSIGHT (away from the desk, via Echo),
(c) Ambient Awareness: a safe filter that surfaces only the real decision.

---

# ⭐ THE SHARP EDGE — Ambient Awareness (the project's identity)

> This is the capability that moves the project from "MCP wrapper" to "creative
> agentic add-on." The demo is built on it, the submission headline is it.
> UC-1..12 are its infrastructure.

## Problem (why it is mandatory)
An autonomous agent working for hours hits DOZENS of approval points (create file,
run test, install package, delete line...). If they all come by voice, KiroWhisper
becomes torture — because VOICE CANNOT BE SCANNED LIKE A SCREEN. On a screen you
skim 20 approvals in 5 seconds; by voice, 20 approvals = 20 interruptions. For a
blind developer this makes voice approval UNUSABLE.

## Solution — three buckets
KiroWhisper does not talk constantly. It waits quietly in the background, sees ALL
of Crew's approval requests (`GET /api/approvals`), classifies each by risk, and:
1. **Silently pass (rule-certain low risk):** read/list/search operations, once the
   user has trusted the session -> auto-approve (`action:"approved"`), don't disturb
   the user. This is the bucket that fires most in practice.
2. **Silently block (catastrophic only):** a narrow, tested deny list — `rm -rf /`,
   `curl … | sh`, `mkfs`, `dd of=/dev/…`, fork bomb -> auto-reject. **In practice this
   rarely fires: Crew's own agent already refuses the worst commands before they ever
   reach an approval (see Friction Log F16), so this is defense-in-depth, not the
   headline.** Merely-risky commands (e.g. a scoped `rm -rf /tmp/x`) are NOT blocked;
   they are surfaced.
3. **Surface to the user (real decision):** irreversible but possibly legitimate,
   requires intent -> ONLY these come by voice, highest risk first, read aloud.

Then, when the user asks, a "while you were away" summary (`get_status`):
> "Since you last checked, Crew asked for two approvals. I passed one as safe. Crew
> has two active sessions, and one decision is waiting for you: it deletes
> old_notes.txt, which is irreversible. Do you want to hear it?"

(This exact shape was verified live on Alexa against the real backend.)

## Why it is creative (not a wrapper)
Crew hands over all approvals equally. The intelligence is in OUR layer:
- Classify each approval by risk (Bedrock + rules): reversible? shell? touching a
  secret? how many lines? (Risk Radar = this step.)
- Decide: pass / block / surface.
- Accumulate and summarize: turn noise into signal.

## Safety principle (critical) — defense-in-depth, verified in code
- **Deterministic rules first, model only for the ambiguous.** Rules flag danger and
  clear read-only; Bedrock is consulted only when rules are inconclusive and returns
  UNKNOWN (never LOW) on any doubt.
- CONSERVATIVE filter: if unsure, ALWAYS surface to the user (safe default; same
  spirit as Crew's "deny on silence").
- **Trust never becomes a hole:** session trust auto-approves LOW only when a *rule*
  is certain (read-only); a model-guessed LOW is still surfaced even under trust.
  *(Verified live: a file-read Crew didn't flag read-only was NOT auto-approved.)*
- **Every voice approval takes two confirmations:** the first "approve" only asks
  "are you sure?"; the action applies only on an explicit second confirmation.
- The user can ALWAYS hear what happened ("Since you last checked… I passed one as safe").
- Every decision is logged (audit; responsible AI).

## Spike-reality: PROVEN ✅
- `GET /api/approvals` -> all pending approvals (tool, purpose, input). ✅
- permission meta: `is_read_only`, `is_shell`, diff -> the RAW DATA for risk
  classification is already there. ✅
- `action:"approved"` (pass) / `"rejected"` (block) / surface to user. ✅
- `action:"trust"` -> "always pass this kind" (a learning filter). ✅
- Bedrock (AWS Builder): raw diff/tool -> risk level + voice-friendly summary.

## Priority: CORE (the project's identity — the demo is built on it)

---

# INFRASTRUCTURE USE CASES (UC-1 .. UC-12)

> These are the infrastructure of the "colleague" experience. Necessary but NOT a
> difference on their own. Ambient Awareness runs on top of them.

## UC-1 — Ask status (PULL / "while you were away" digest)
- **Actor:** Deniz. **Trigger:** "get status" / "what did I miss?"
- **Flow:** The system reports what happened since the last check: what Crew asked
  for, what it passed/blocked automatically, what the user decided, how many are
  still waiting. Ends with a question so the voice session stays open.
- **Status:** ✅ Built and **verified live on Alexa** (`get_status` tool +
  audit digest + persisted checkpoint). Matched the backend exactly.
- **Priority:** CORE

## UC-2 — Approve (always two-step confirm by voice)
- **Actor:** Deniz. **Trigger:** "approve it."
- **Flow:** The decision is read aloud first; the first "approve" only asks "are you
  sure?"; an explicit second confirmation applies it. Applies to every decision, not
  just high-risk, so a stray "yes" can never act on its own.
- **Status:** ✅ Built and **verified live on Alexa**: the target file was deleted only
  after the second confirmation; the backend showed the resolve.
- **Priority:** CORE
- **GOTCHA:** action="approved" (past tense!) — "approve" silently falls to rejected;
  we also verify the approval's real resolved state instead of trusting `{"ok":true}`.

## UC-3 — Reject -> sub-options
- **Actor:** Deniz. **Trigger:** "No."
- **Flow:** First reassure ("I didn't do it"), then three spoken options: SKIP /
  PAUSE / CANCEL (always same order/words). Safe default + timeout = PAUSE. Cancel
  asks for extra confirmation.
- **Spike:** ⚠️ `action:"rejected"` = skip/continue (native, ✅). "Pause" = reject +
  send no new message (our mapping). "Cancel" = stop the slot. We open the native
  binary model into three.
- **Priority:** CORE

## UC-4 — Hear the result (task done)
- **Actor:** system->Deniz. **Trigger:** task completed.
- **Flow:** "Done. 3 files changed, tests passed." (voice-friendly summary)
- **Spike:** ✅ `GET /api/spawn/<id>` -> done, turns, result messages.
- **Priority:** CORE

## UC-5 — The colleague calls you (PUSH / proactive)
- **Actor:** system->Deniz. **Trigger:** a new real decision passed the filter.
- **Flow:** The system speaks up on its own: "KiroWhisper: I need your approval on
  task 3." -> user "what is it?" -> flow.
- **Reality check (important):** On the real Alexa+ path this is **not possible today**
  — MCP is request/response and Alexa+ has no proactive channel for add-ons (see
  Friction Log F7). We implemented it only in the web dev console (Ambient's
  `on_surface` -> SSE -> spoken alert). Because the dev console runs on the same
  machine where Crew already sends notifications, we **do not headline this** in the
  submission; the product is the pull model (UC-1) on Alexa.
- **Priority:** FUTURE (needs an Alexa+ proactive channel) — kept as a design point,
  not a demo claim.

## UC-6 — "Always approve from now on" (trust / session trust)
- **Actor:** Deniz. **Trigger:** "For this task, always approve."
- **Flow:** The system auto-approves the remaining (low-risk) steps in the session.
- **Spike:** ✅ `action:"trust"`. NOTE: presented only with a low-risk framing.
- **Priority:** DIFFERENTIATOR

## UC-7 — Context tracking (state across sessions)
- **Actor:** Deniz. **Trigger:** "Which one failed?"
- **Flow:** The system tracks which of several tasks is being referred to. "Task 2 —
  tests are red. Want me to open it?"
- **Spike:** ✅ `GET /api/spawn` (list + states). The "which" resolution is ours (short memory).
- **Priority:** DIFFERENTIATOR (the rules consider this "creative")

## UC-8 — Mid-task redirect
- **Actor:** Deniz. **Trigger:** while the agent works, "Stop, don't touch that file, run tests first."
- **Flow:** Intervene in the running slot, change direction.
- **Spike:** ⚠️ `POST /api/chat {slot,message}` to the running slot (to be tested).
  The capability ChatGPT Voice highlights; for us, "interrupting the colleague."
- **Priority:** FUTURE (v2)

## UC-9 — Clarifying question (the agent asks YOU)
- **Actor:** system->Deniz. **Trigger:** the agent needs an open-ended choice.
- **Flow:** "Two ways: token-based or session-based? Which do you want?" -> voice
  choice. Not just approval, REAL DIALOGUE -> completes the "colleague" metaphor.
- **Spike:** ✅ (data exists) slot fields: `waiting_for_input`, `needs_input`,
  `has_options`, `options` (seen in the spike). Technically feasible.
- **Priority:** DIFFERENTIATOR (completes the colleague metaphor)

## UC-10 — Multi-task "standup" summary
- **Actor:** Deniz. **Trigger:** "What's the overall status?" / morning briefing.
- **Flow:** "2 of 3 tasks done, one waiting for approval, one failed." (parallel summary)
- **Spike:** ✅ `GET /api/spawn` + `/api/status`. Bedrock summary.
- **Priority:** DIFFERENTIATOR

## UC-11 — Safe decision record (audit)
- **Actor:** system. **Trigger:** every approve/reject/auto-pass/auto-block decision.
- **Flow:** each decision is appended to an audit log (timestamp, request id, risk,
  action, who decided), secrets masked. This is the source of the "while you were away"
  digest (UC-1) and the human-in-the-loop delivery guarantee — e.g. "you rejected the
  delete at 08:16; I passed two reads as safe."
- **Status:** ✅ Built and used live by `get_status`; logging is entirely our layer.
- **Priority:** DIFFERENTIATOR (responsible-AI points; the HITL "delivery guarantee" principle)

## UC-12 — Failure notification
- **Actor:** system->Deniz. **Trigger:** a task failed.
- **Flow:** "Task 2 failed, tests are red. Want details?"
- **Spike:** ✅ `task_complete` also arrives on failure; `GET /api/spawn/<id>` state.
- **Priority:** CORE (part of the result loop)

---

# Starting new tasks — scope decision
- KiroWhisper's FOCUS = OVERSIGHT (monitor + approve), NOT starting new work.
- Starting a new task by voice (`POST /api/spawn`) is technically feasible (spike ✅)
  but it moves us toward the "voice coding" commodity -> OUT OF SCOPE (v2). The
  difference is in oversight.

---

# Scope summary (requirement priority)
- **CORE (built + verified live on Alexa):** Ambient Awareness + UC-1 (status digest),
  UC-2 (approve with two-step confirmation), UC-3 (reject), UC-6 (session trust,
  rule-certain only).
- **DIFFERENTIATOR:** UC-7, UC-9, UC-10, UC-11 (audit).
- **FUTURE (v2, "future work" in submission):** UC-5 (needs an Alexa+ proactive
  channel), UC-8 (mid-task redirect), UC-12 (failure push), voice-starting new tasks.

# Demo storyline (Alexa-first; verified flows only)
The product surface is the Alexa skill over our self-hosted MCP server (via the
`alexa-skill-mcp-bridge` + AgentCore). The web console is a dev tool, not shown as
the product.
1. HOOK (0-30s): the maker's own pain — an autonomous Crew, dozens of approvals, the
   fatigue of turning back to the screen; for a blind developer, unusable by voice.
2. AMBIENT AWARENESS (30-110s): on a real Echo / the Alexa console — "Alexa, open
   kiro whisper" -> "get status" (the "while you were away" digest: *asked for two,
   I passed one as safe, one is waiting*) -> "what needs my decision" reads the
   decision aloud -> "approve it" -> **two-step confirmation** -> "yes" -> applied.
   All of this was verified live against the real backend.
3. DEPTH (110-150s): defense-in-depth — deterministic rules first, Bedrock for the
   ambiguous, trust that never auto-approves a guess, two-step confirm on every action.
4. CURB-CUT (150-180s): "a comfort for me; for a blind developer, being able to
   oversee an autonomous agent without any dependence on a screen — because voice
   alone cannot be scanned, and without a filter it is unusable."
