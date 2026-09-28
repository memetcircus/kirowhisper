# KiroWhisper

**Voice oversight for autonomous Kiro Crew — hear only the decisions that matter.**

KiroWhisper lets you supervise an autonomous [Kiro Crew](https://github.com/kirodotdev/KiroCrew)
**by voice, without looking at a screen**. Crew works for hours on its own and
pauses at dozens of approval points ("create this file?", "run this migration?",
"delete these lines?"). KiroWhisper watches every one of them, classifies each by
risk, silently handles the safe and the clearly dangerous, and speaks up **only for
the decisions that genuinely need you.**

> **A colleague, not a tool.** Not a command-obeying assistant — a teammate in the
> next room that consults you when it matters and proceeds safely when it doesn't.

Built for the **Amazon "Build, Ship, Shape" Developer Hackathon** — Alexa+ track
(MCP), with the **AWS Builder** mini-challenge (Amazon Bedrock).

> **Honest disclosure:** The official Alexa+ MCP add-on toolkit is not yet publicly
> available, so the primary demo surface is a **rules-compliant simulation** (a web UI
> using the browser's own speech-to-text and text-to-speech, driven by your own voice).
> Everything behind it is real: a genuine MCP server, the real Kiro Crew Gateway, and
> Amazon Bedrock. We *additionally* ran the full flow on a **real Echo device and the
> Alexa developer console** via the open-source
> [`alexa-skill-mcp-bridge`](https://github.com/KayLerch/alexa-skill-mcp-bridge)
> (an Alexa Skill → Amazon Bedrock AgentCore agent → our MCP server), where
> decision-read, safe-reject, and a high-risk two-step approve all worked by voice
> against the live backend.

---

## The sharp edge: Ambient Awareness

Voice cannot be scanned like a screen. On a screen you skim 20 approvals in five
seconds; by voice, 20 approvals are 20 interruptions. For a blind developer, that
makes naive "voice approval" unusable. **Ambient Awareness** is the answer:

1. **Silently pass** low-risk, reversible actions (read a file, run a test).
2. **Silently block** clearly dangerous ones that match an explicit deny rule.
3. **Surface — by voice — only** what genuinely needs a human decision.

Then, when you ask, it summarizes the noise it handled for you:

> *"In the last two hours Crew did 23 steps. I passed 19 as safe, blocked 3
> dangerous ones, and 1 is waiting for you: it deletes `auth.js`, which is
> irreversible, so I wasn't sure."*

This is why accessibility here is a **requirement, not a label**: without the
filter, eyes-free voice oversight simply doesn't work. And it helps everyone away
from the screen — the curb-cut effect.

---

## How the risk filter actually works (defense-in-depth)

We're honest about this: **the classifier is deterministic guardrails first, a model
only for the ambiguous cases** — not "an AI decides everything."

1. **Deterministic rules run first** (`risk.py`). Fast, testable pattern rules flag the
   clearly dangerous — shell commands, `rm -rf`, `DROP TABLE`, force-push, secret/`.env`
   exposure — as HIGH, and clearly reversible read-only ops as LOW. Rules only ever
   *raise* risk; they never downgrade a HIGH.
2. **Amazon Bedrock (Nova) handles only what the rules can't decide.** When the rules
   are inconclusive, the model classifies. On any error or doubt it returns **UNKNOWN**,
   never LOW.
3. **When unsure, surface.** HIGH and UNKNOWN always reach a human. Nothing destructive
   is silently downgraded.

Two safety properties fall out of this, and both are enforced in code and tested:

- **Trust never becomes a hole.** "Trust this session" auto-approves LOW steps — but
  *only rule-certain* LOW (e.g. a verified read-only op). A LOW that the *model merely
  guessed* is still surfaced, even under trust. Security leans on what we know for sure,
  not on a guess. *(Verified live: with trust on, a file-read that Crew did not flag
  read-only was not auto-approved — it still asked.)*
- **High-risk needs a second confirmation.** By voice, the first "approve" only asks
  "are you sure?"; the decision is applied only on an explicit second confirmation. A
  stray "yes" can never fire a destructive step on its own.

A blacklist of patterns is not a security product — so we don't oversell it. It's a
fast, reliable first layer that fails safe (toward surfacing), backed by the model for
nuance and by a human for anything uncertain.

---

## Architecture

```
 You (voice)                          KiroWhisper                         Kiro Crew
 ───────────                          ───────────                         ─────────
  speak ──STT──▶  Voice UI  ──HTTP──▶  MCP server / JSON bridge
                 (Web Speech)          │
                                       ├─ Ambient engine (polling, three buckets)
                                       ├─ Risk classifier (rules → Bedrock)
                                       ├─ Summarizer (Bedrock, voice-friendly)
                                       └─ Gateway client ──REST──▶ Crew Gateway
  hear ◀──TTS──   spoken reply  ◀──────┘                          (localhost:5476)
```

- **The intelligence is ours, the transport is swappable.** The same core services
  power both a real **MCP server** (Streamable HTTP, spec 2025-11-25) for Alexa+/MCP
  clients, and a **web voice UI** for the demo.
- **Amazon Bedrock** (Nova Lite, `us-east-1`) does nuanced risk classification and
  voice-friendly summaries. Deterministic rules run first and always win in the
  safe direction; Bedrock is consulted only when the rules are inconclusive.
- **Fail-safe by default:** anything uncertain is surfaced to you, never silently
  approved. Destructive actions require explicit confirmation.

Full specs live in [`.kiro/specs/kirowhisper/`](.kiro/specs/kirowhisper/)
(requirements → design → tasks), authored with Kiro's spec-driven workflow.

---

## Quick start

**Prerequisites**
- Python 3.12+
- A running [Kiro Crew](https://github.com/kirodotdev/KiroCrew) Gateway on
  `localhost:5476` (the `kirocrew` CLI on your `PATH`, signed in).
- For real Bedrock summaries: AWS credentials with Bedrock model access in
  `us-east-1` (optional — a deterministic fallback works without it).

**Install**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

**Run the voice demo** (web UI with your own voice)
```bash
python -m kirowhisper voice
# open http://127.0.0.1:8800 — tap the ring and say "what's up?", "approve", "no"
```

**Run as an MCP server** (for Alexa+/MCP clients, Streamable HTTP)
```bash
python -m kirowhisper
# serves the MCP tools over stateless Streamable HTTP on 127.0.0.1:8000/mcp
```

**MCP tools exposed:** `get_status`, `get_pending_decisions`, `approve_top`,
`reject_top`, `approve`, `reject`, `trust_session`, `summarize`.

The voice path is a two-call flow that's robust on assistants with no elicitation
back-channel: `get_pending_decisions` speaks the highest-risk decision first, then
`approve_top` / `reject_top` acts on it with no request id. **High-risk decisions
require a second confirmation** — the first `approve_top` only asks "are you sure?",
and a second call applies it. The server runs **stateless** (each request stands
alone), so a long-lived client behind a tunnel never hits a dead session.

**Configuration** (all optional, via environment):
`KIROWHISPER_GATEWAY_URL`, `KIROWHISPER_TOKEN_CMD`, `AWS_REGION`,
`KIROWHISPER_BEDROCK_FAST_MODEL`, `KIROWHISPER_POLL_INTERVAL`.

---

## How it works with Kiro Crew

KiroWhisper talks to the Crew Gateway's REST API (verified live during a feasibility
spike, see [`spike/`](spike/)):
- `GET /api/status`, `GET /api/approvals` — read state and pending approvals.
- `POST /api/chat/slots/<slot>/approve` — resolve an approval
  (`{"action":"approved"|"rejected"|"trust", "request_id":...}`).

The Ambient engine polls for pending approvals, classifies each, and applies the
three-bucket policy — auto-approving trusted low-risk steps, blocking explicit
denies, and surfacing the rest to you by voice.

---

## Testing

```bash
pytest            # unit + bridge tests (no network/model needed)
KIROWHISPER_RUN_INTEGRATION=1 pytest tests/test_gateway_integration.py  # needs a live Gateway
```

The risk classifier, decision policy, and fail-safe behavior are covered by a
deterministic test suite so the security guarantees are locked against regression.

---

## Tracks

- **Primary:** Alexa+ (MCP server; Alexa+ layer simulated per hackathon rules).
- **Mini-challenge:** AWS Builder (Amazon Bedrock for risk classification and
  summarization).

## License

[MIT](LICENSE).
