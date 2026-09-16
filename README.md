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

> **Honest disclosure:** The Alexa+ MCP add-on toolkit is not yet publicly
> available, so the Alexa+ interaction layer here is a **rules-compliant
> simulation** (a web UI using the browser's own speech-to-text and text-to-speech,
> driven by your own voice). Everything behind it is real: a genuine MCP server,
> the real Kiro Crew Gateway, and Amazon Bedrock. Only the "Alexa+" surface is simulated.

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
# serves the MCP tools over Streamable HTTP
```

**MCP tools exposed:** `get_status`, `get_pending_decisions`, `approve`, `reject`,
`trust_session`, `summarize`.

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
