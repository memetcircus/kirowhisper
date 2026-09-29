# KiroWhisper

**Voice oversight for autonomous Kiro Crew — hear only the decisions that matter.**

KiroWhisper lets you supervise an autonomous [Kiro Crew](https://github.com/kirodotdev/KiroCrew)
**by voice, through Alexa, without looking at a screen**. Crew works for hours on its
own and pauses at dozens of approval points ("create this file?", "run this
migration?", "delete these lines?"). KiroWhisper watches every one of them, classifies
each by risk, silently handles the safe and the clearly dangerous, and speaks up
**only for the decisions that genuinely need you.**

> **A colleague, not a tool.** Not a command-obeying assistant — a teammate in the
> next room that consults you when it matters and proceeds safely when it doesn't.

Built for the **Amazon "Build, Ship, Shape" Developer Hackathon** — **Alexa+ track**
(self-hosted MCP server), with the **AWS Builder** mini-challenge (Amazon Bedrock,
Bedrock AgentCore, Strands, Kiro Crew).

> **What runs where.** KiroWhisper is a real, self-hosted **MCP server** (spec
> 2025-11-25, Streamable HTTP) wired to the real Kiro Crew Gateway and Amazon Bedrock.
> The official Alexa+ MCP add-on toolkit is not yet publicly available, so we reach
> Alexa through the open-source
> [`alexa-skill-mcp-bridge`](https://github.com/KayLerch/alexa-skill-mcp-bridge):
> an Alexa Skill hands each spoken turn to an agent on Amazon Bedrock AgentCore, which
> calls our MCP server's tools and speaks the result. The full flow runs on a real Echo
> device and in the Alexa developer console.

---

## The sharp edge: Ambient Awareness

Voice cannot be scanned like a screen. On a screen you skim 20 approvals in five
seconds; by voice, 20 approvals are 20 interruptions. For a blind developer, that
makes naive "voice approval" unusable. **Ambient Awareness** is the answer:

1. **Silently pass** low-risk, reversible actions (once you trust the session).
2. **Silently block** clearly dangerous ones that match an explicit deny rule.
3. **Surface — by voice — only** what genuinely needs a human decision, highest
   risk first, and read it aloud so you know exactly what you're approving.

This is why accessibility here is a **requirement, not a label**: without the
filter, eyes-free voice oversight simply doesn't work. And it helps everyone away
from the screen — the curb-cut effect.

### What a session sounds like

```
You:   Alexa, open kiro whisper.
Alexa: Welcome to kirowhisper. Say "get status" or "what needs my decision".
You:   Get status.
Alexa: One decision is waiting for you, and the crew has four active sessions.
You:   What needs my decision?
Alexa: The most important one: a shell command that removes a file. This may be
       irreversible. Do you want to approve it or reject it?
You:   Approve it.
Alexa: This is high-risk. To confirm, are you sure you want to approve this?
You:   Yes.
Alexa: Approved. The task is continuing.
```

This flow was run live in the Alexa developer console against a real Kiro Crew
(Alexa's wording varies slightly turn to turn) and verified against the backend: the
file was deleted only after the second confirmation.

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
- **Every voice approval needs a second confirmation.** The first "approve" only asks
  "are you sure?"; the decision is applied only on an explicit second confirmation. A
  stray "yes" can never fire a step on its own.

A blacklist of patterns is not a security product — so we don't oversell it. It's a
fast, reliable first layer that fails safe (toward surfacing), backed by the model for
nuance and by a human for anything uncertain.

---

## Architecture

```
 Echo / Alexa                 AWS                             Your machine
 ────────────                 ───                             ────────────
  "what needs      ──▶  Alexa Skill (Lambda)
   my decision?"              │
                              ▼
                        Bedrock AgentCore agent        ──HTTPS tunnel──▶  KiroWhisper MCP server
                        (Strands + Nova, from                            (Streamable HTTP, stateless)
                         alexa-skill-mcp-bridge)                          ├─ Ambient engine (three buckets)
                              │                                           ├─ Risk classifier (rules → Bedrock)
  spoken reply     ◀──────────┘                                           ├─ Summarizer (voice-friendly)
                                                                          └─ Gateway client ──▶ Kiro Crew Gateway
                                                                                                (localhost:5476)
```

- **The intelligence is ours; the voice transport is swappable.** Risk classification,
  the three-bucket policy, the two-step confirmation and the spoken wording all live in
  the MCP server. The Alexa side only turns speech into tool calls and back.
- **Amazon Bedrock** (Nova Lite, `us-east-1`) does nuanced risk classification and
  voice-friendly summaries. Deterministic rules run first and always win in the safe
  direction; Bedrock is consulted only when the rules are inconclusive.
- **Fail-safe by default:** anything uncertain is surfaced to you, never silently
  approved.
- The server runs **stateless** (each request stands alone), so a long-lived Alexa agent
  behind a tunnel never hits a dead MCP session.

Full specs live in [`.kiro/specs/kirowhisper/`](.kiro/specs/kirowhisper/)
(requirements → design → tasks), authored with Kiro's spec-driven workflow.

---

## Quick start

### Prerequisites
- Python 3.12+
- A running [Kiro Crew](https://github.com/kirodotdev/KiroCrew) Gateway on
  `localhost:5476` (the `kirocrew` CLI on your `PATH`, signed in).
- AWS credentials with Bedrock model access in `us-east-1` (optional for the MCP
  server — a deterministic fallback works without it; required for the Alexa path).

### 1. Run the MCP server

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m kirowhisper
# serves the MCP tools over stateless Streamable HTTP on 127.0.0.1:8000/mcp
```

**MCP tools exposed:** `get_status`, `get_pending_decisions`, `approve_top`,
`reject_top`, `approve`, `reject`, `trust_session`, `summarize`.

The voice path is a two-call flow that works without an elicitation back-channel:
`get_pending_decisions` reads the highest-risk decision aloud, then `approve_top` /
`reject_top` acts on it with no request id. `approve_top` always takes two calls: the
first only asks the user to confirm, the second applies it.

### 2. Expose it to AWS

The AgentCore agent runs in AWS and cannot reach `localhost`, so publish the server
through a tunnel:

```bash
cloudflared tunnel --url http://localhost:8000 --http-host-header localhost:8000
# on networks that block QUIC (UDP 7844), add: --protocol http2
```

Note the `https://<name>.trycloudflare.com` URL it prints. Quick-tunnel URLs change
on every restart.

### 3. Connect Alexa (via `alexa-skill-mcp-bridge`)

Requires Node 22+, Docker (running), the AWS CDK, and the ASK CLI configured with the
**same Amazon account your Echo uses**.

```bash
git clone https://github.com/KayLerch/alexa-skill-mcp-bridge
cd alexa-skill-mcp-bridge && npm install
# in .env:  BRIDGE_MCP_URL=https://<name>.trycloudflare.com/mcp
npm run generate        # builds the interaction model from our live MCP tools
npm run deploy          # CDK: AgentCore runtime + skill Lambda (us-east-1)
npm run skill:deploy    # deploys the Alexa Skill
```

KiroWhisper relies on a few changes to the bridge that we made while testing on real
Alexa (see [Friction Log](docs/FRICTION_LOG.md) F11–F15):
- reconnect-and-retry once on a stale MCP session or a changed tool schema;
- system-prompt rules that the agent never approves or rejects without an explicit
  command, and reads a decision aloud before asking;
- sample utterances for "approve it" / "reject it".

Then enable testing in the Alexa developer console (or on your Echo) and say
**"Alexa, open kiro whisper"**, followed by **"what needs my decision"** or
**"get status"**. The explicit "open …" / "ask kiro whisper …" form routes reliably to
the skill.

**Configuration** (all optional, via environment):
`KIROWHISPER_GATEWAY_URL`, `KIROWHISPER_TOKEN_CMD`, `AWS_REGION`,
`KIROWHISPER_BEDROCK_FAST_MODEL`, `KIROWHISPER_POLL_INTERVAL`.

### Developer tool: web voice console (not the product surface)

`python -m kirowhisper voice` opens a browser console at `http://127.0.0.1:8800` that
talks to the same core services with your own voice (browser speech-to-text, host
text-to-speech). We use it for fast local iteration without deploying to AWS. It is a
**development aid**, not the Alexa experience, and its intent handling is simpler than
the MCP tools'.

---

## How it works with Kiro Crew

KiroWhisper talks to the Crew Gateway's REST API (verified live during a feasibility
spike, see [`spike/`](spike/)):
- `GET /api/status`, `GET /api/approvals` — read state and pending approvals.
- `POST /api/chat/slots/<slot>/approve` — resolve an approval
  (`{"action":"approved"|"rejected"|"trust", "request_id":...}`), then verify the
  approval's real resolved state instead of trusting `{"ok": true}`.

The Ambient engine polls for pending approvals, classifies each, and applies the
three-bucket policy.

---

## Testing

```bash
pytest            # unit tests (no network/model needed)
KIROWHISPER_RUN_INTEGRATION=1 pytest tests/test_gateway_integration.py  # needs a live Gateway
```

The risk classifier, decision policy, trust boundary, two-step confirmation and
fail-safe behavior are covered by a deterministic test suite so the security
guarantees are locked against regression.

---

## Tracks

- **Primary:** Alexa+ — self-hosted MCP server (spec 2025-11-25, Streamable HTTP),
  exercised end to end through an Alexa Skill on a real Echo and the Alexa developer
  console.
- **Mini-challenge:** AWS Builder — Amazon Bedrock (risk classification and spoken
  summaries), Bedrock AgentCore + Strands (the Alexa agent), and Kiro Crew (the
  supervised agent and our development tool).

See also: [Product Feedback](docs/PRODUCT_FEEDBACK.md) ·
[Friction Log](docs/FRICTION_LOG.md) · [Use Cases](docs/USE_CASES.md)

## License

[MIT](LICENSE).
