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
1. **Silently pass (low risk):** read files, tests, reversible edits -> auto-approve
   (`action:"approved"`), don't disturb the user.
2. **Silently block/hold (obvious danger):** `rm -rf`, prod push, secret logging ->
   auto-stop (`action:"rejected"` or hold), summarize "I blocked this" later.
3. **Surface to the user (real decision):** irreversible but possibly legitimate,
   requires intent -> ONLY these come by voice.

Then, when the user asks, a summary:
> "In the last 2 hours Crew did 23 steps. I passed 19 as safe, blocked 3 dangerous
> ones, and 1 is waiting for you: it deletes auth.js, irreversible, I wasn't sure."

## Why it is creative (not a wrapper)
Crew hands over all approvals equally. The intelligence is in OUR layer:
- Classify each approval by risk (Bedrock + rules): reversible? shell? touching a
  secret? how many lines? (Risk Radar = this step.)
- Decide: pass / block / surface.
- Accumulate and summarize: turn noise into signal.

## Safety principle (critical)
- CONSERVATIVE filter: if unsure, ALWAYS surface to the user (safe default; same
  spirit as Crew's "deny on silence").
- The user can ALWAYS see what was passed ("I passed 19, want to hear them?").
- Nothing destructive passes silently — only clearly low-risk/reversible items.
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

## UC-1 — Ask status (PULL / summary)
- **Actor:** Deniz. **Trigger:** "Kiro, what's up?"
- **Flow:** The system fetches Crew's state + pending approvals and produces a
  voice-friendly summary. "It has one thing: waiting for your approval to delete
  the old login in auth.js. Nothing else pending."
- **Spike:** ✅ `GET /api/status` + `GET /api/approvals`. Summary via Bedrock.
- **Priority:** CORE

## UC-2 — Approve (high risk -> double-confirm)
- **Actor:** Deniz. **Trigger:** "Approve."
- **Flow:** If destructive/irreversible, the system re-confirms intent ("this
  deletes 42 lines, irreversible, are you sure?") -> clear "yes" -> approve.
- **Spike:** ✅ `POST /api/chat/slots/<slot>/approve {action:"approved", request_id}`
  -> `{"ok":true}`, the file ACTUALLY changed. Risk data: is_shell/is_read_only/diff.
- **Priority:** CORE
- **GOTCHA:** action="approved" (past tense!) — "approve" silently falls to rejected.

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

## UC-5 — The colleague calls you (PUSH / proactive) ⭐
- **Actor:** system->Deniz. **Trigger:** a new approval/event appeared, the user is not at the screen.
- **Flow:** The system speaks up on its own: "KiroWhisper: I need your approval on
  task 3." (music ducks / light / short alert) -> user "what is it?" -> flow.
- **Spike/rules:** ⚠️ WILL BE STAGED (Emerson: legitimate in simulation). Technical
  basis: background `GET /api/approvals` POLLING -> trigger spoken alert on a new
  approval. The data is real; the "speaking on its own" is staged.
- **Priority:** CORE (the soul) — but with Ambient Awareness: only the "real
  decision" that passes the filter is surfaced proactively, not the noise.

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
- **Actor:** system. **Trigger:** every approve/reject/filter decision.
- **Flow:** "Deniz rejected the delete approval at 08:16 / KiroWhisper blocked 3
  dangerous operations" -> logged, summarizable on request.
- **Spike:** ✅ decisions are produced in our layer; logging is our layer. (Crew also has security_events.)
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
- **CORE (must-have):** Ambient Awareness + UC-1,2,3,4,5,12
- **DIFFERENTIATOR (once core works):** UC-6,7,9,10,11
- **FUTURE (v2, "future work" in submission):** UC-8, voice-starting new tasks

# Demo storyline (from these use cases)
1. HOOK (0-30s): the maker's own pain (3 projects, constant approvals, the fatigue
   of turning back to the screen).
2. AMBIENT AWARENESS (30-100s): Crew works autonomously, KiroWhisper filters
   silently; surfaces only 1 real decision by voice (UC-5->UC-1->UC-2 double-confirm).
   "I passed 19."
3. DEPTH (100-150s): how risk classification + safe approval work (Bedrock).
4. CURB-CUT (150-180s): "a comfort for me; for a blind developer, being able to
   oversee an autonomous agent without any dependence on a screen — because voice
   alone cannot be scanned, and without a filter it is unusable."
