# Implementation Plan — KiroWhisper

> Kiro spec-driven development. Each task is incremental, testable, and builds on
> the previous one. Requirement references point to `requirements.md`.
> Build order: Crew bridge first (proven), then intelligence (Ambient), then the
> face (MCP + voice).
>
> Scope tag: [CORE] first and flawless; [DIFF] once core works;
> [v2] "future work" in the submission.

## Phase 0 — Project skeleton and environment

- [x] 0.1 Set up the Python 3.12 project skeleton (`src/kirowhisper/`,
  `pyproject.toml`, venv, `pytest`, `ruff`). Deps: `httpx`, MCP Python SDK,
  `boto3` (Bedrock).
  - _Design: Technical decisions / Structure_

- [x] 0.2 Configuration layer: read Gateway URL, token source (`kirocrew token`),
  Bedrock region (us-east-1), and model ids from a central config.
  - _Requirements: NFR-5; Design: Technical decisions_

## Phase 1 — Crew Gateway Client  [CORE]

- [x] 1.1 `gateway_client.py`: thin REST client with `?token=` + `Origin` auth.
  `get_status`, `list_pending_approvals`, `get_slot`, `resolve`, `send_message`,
  `spawn`, `get_task_result`. Fetch token from `kirocrew token`, refresh on expiry.
  - _Requirements: R1, R4, R5, R12.2; Design: Component 1_
  - _Note: derived from spike/ scripts; auth and the action="approved" gotcha are proven._

- [x] 1.2 Unit tests for `gateway_client` (mock HTTP): auth header/param correct,
  `resolve` body is `{"action":"approved","request_id":...}`, exceptions on errors.
  - _Requirements: R5.3, R5.4_

- [x] 1.3 Integration smoke test against a real local Gateway: `get_status` +
  `list_pending_approvals` work (productized version of the spike).
  - _Requirements: R1.1, R1.2_

## Phase 2 — Data models and Audit  [CORE]

- [x] 2.1 Data models: `Approval`, `RiskAssessment`, `Decision`,
  `PendingDecision`, `AuditEntry` (dataclass/pydantic). _(done in 1.1)_
  - _Design: Data models_

- [ ] 2.2 `audit.py`: append-only local log (ts, id, risk, decision, reason).
  Secret masking. Read API for summaries.
  - _Requirements: R10, NFR-1; Design: Component 7_

## Phase 3 — Risk Classifier  [CORE — the project's intelligence]

- [ ] 3.1 `risk.py` (a) deterministic rule layer: `is_read_only`->LOW,
  `is_shell`->>=HIGH, destructive patterns (`rm -rf`, `DROP`, `force`,
  `.env`/secret, broad deletion)->HIGH, unclear->defer. Rules tighten one way only.
  - _Requirements: R2.2, R2.3, R2.4, R2.5_

- [ ] 3.2 `risk.py` (b) Bedrock layer: raw tool+purpose+diff -> structured risk +
  reason. Error/unsure -> UNKNOWN. Called only when rules say "unclear."
  - _Requirements: R2.1, R2.6; Design: Component 3_

- [ ] 3.3 Risk classifier unit tests: known dangerous/safe diff sample set; rule
  layer classifies correctly; falls to UNKNOWN on Bedrock error (fail-safe).
  - _Requirements: R2.5, NFR-1_

## Phase 4 — Summarizer  [CORE]

- [ ] 4.1 `summarizer.py`: Bedrock voice-friendly summaries — approval, status,
  ambient. Short, priority-ordered, not raw diff, <=2-3 options.
  - _Requirements: R4.4, NFR-3; Design: Component 4_

- [ ] 4.2 Summarizer tests: long diff -> short voice text; no secret leakage.
  - _Requirements: NFR-1, NFR-3_

## Phase 5 — Ambient Awareness Engine  [CORE — the heart]

- [ ] 5.1 `ambient.py` polling loop (asyncio, ~2-3s): detect new approvals
  idempotently (remember seen). Gateway down -> retry, NO auto-approve.
  - _Requirements: R1.1, R1.3, R1.4_

- [ ] 5.2 Decision policy (`policy.decide`): LOW+trust->AUTO_APPROVE,
  explicit-deny->AUTO_BLOCK, HIGH/UNKNOWN->SURFACE. Conservative: unsure->SURFACE.
  Write decision to audit, apply via gateway.resolve.
  - _Requirements: R3.1, R3.2, R3.3, R3.4, R3.5_

- [ ] 5.3 SURFACE queue + snapshot API (how many AUTO/BLOCK/SURFACE) — the source
  of the status summary ("I passed 19...").
  - _Requirements: R4.3_

- [ ] 5.4 Ambient engine tests (fake Gateway): three-bucket decisions correct;
  idempotency; fail-safe (Gateway/Bedrock error -> SURFACE, never silent approve).
  - _Requirements: R1.4, R3.3, R3.5, NFR-1_

## Phase 6 — MCP Server  [CORE — Alexa+ runtime requirement]

- [ ] 6.1 `mcp_server.py`: MCP Python SDK, **Streamable HTTP**. Tools:
  `get_status`, `get_pending_decisions`, `approve`, `reject`, `trust_session`,
  `summarize`. Each tool calls the relevant core service (real MCP at runtime).
  - _Requirements: R12.1, R12.2; Design: Component 5_

- [ ] 6.2 `approve` tool: return double-confirm info if HIGH; on clear approval
  gateway.resolve("approved"). `reject` tool: skip/pause/cancel handling.
  - _Requirements: R5.1, R5.2, R6.1, R6.2, R6.3, R6.4, R6.5_

- [ ] 6.3 Verify the MCP server with MCP Inspector or a test client (tool
  discovery + call + spec 2025-11-25 compliance).
  - _Requirements: R12.2_

## Phase 7 — Voice Interface (simulation)  [CORE]

- [ ] 7.1 `voice_sim/` web interface: microphone -> STT -> MCP tool call ->
  response -> TTS. Low-latency STT/TTS. The user's own voice. No ElevenLabs.
  - _Requirements: R11.1, R11.3, NFR-2_

- [ ] 7.2 Proactive notification: when ambient surfaces something, the interface
  triggers a spoken alert. Simulation honestly labeled in the demo.
  - _Requirements: R7.1, R7.2, R7.3, R11.4_

- [ ] 7.3 End-to-end rehearsal: breakfast scenario (Crew autonomous -> ambient
  filters -> one real decision surfaced -> approve by voice -> file changes).
  - _Requirements: R4, R5, R7; Design: Flow B_

## Phase 8 — Differentiators  [DIFF — once core works]

- [ ] 8.1 Session trust (`trust_session`): LOW auto-approve; HIGH/UNKNOWN still surface.
  - _Requirements: R8_

- [ ] 8.2 Context tracking + clarifying question: multi-task reference mapping;
  `waiting_for_input`/`has_options` -> present options by voice.
  - _Requirements: R9_

- [ ] 8.3 Standup summary + failure notification: multi-task status + failure.
  - _Requirements: R4.2, R7.4 (UC-10, UC-12)_

## Phase 9 — Hackathon deliverables  [CORE — points]

- [ ] 9.1 README: clear setup + run instructions; architecture; honest simulation
  disclosure. Visible open-source LICENSE (shown in About).
  - _Requirements: NFR-5, R12.3_

- [ ] 9.2 Product Feedback doc: for each tool/SDK used (Kiro Crew, MCP SDK,
  Bedrock, STT/TTS) — what worked / what was hard / onboarding / would you reuse.
  - _Requirements: NFR-5_

- [ ] 9.3 Friction Log: frictions encountered during development (auth gotcha,
  action="approved", proactive-speech limitation, etc.) — 10% bonus.
  - _Requirements: NFR-5_

- [ ] 9.4 <3 min demo video: breakfast scenario; human story + genuinely working
  system; curb-cut message. Simulation disclosed honestly.
  - _Requirements: NFR-5, R11.4_

## Phase 10 — Future (v2)  [v2]

- [ ] 10.1 Mid-task redirect (UC-8): intervene in a running slot.
- [ ] 10.2 Voice-starting new tasks (out of scope — commodity risk).
- [ ] 10.3 Real Alexa+ MCP add-on (if the toolkit opens) / real Echo via Kay bridge.

---

## Build order summary
Phase 0 -> 1 (bridge, proven) -> 2 (models/audit) -> 3 (risk = intelligence) ->
4 (summary) -> 5 (Ambient = heart) -> 6 (MCP = Alexa requirement) -> 7 (voice =
face) -> 9 (deliverables, ongoing) -> 8 (diff) -> 10 (v2).

## Core "done" definition (minimum winnable product)
Phases 1-7 + 9 complete: a system connected to Crew, filtering approvals by risk,
surfacing only the real decision by voice, approved by real voice and triggering
the operation in Crew, packaged as an MCP server, demoable via simulation. The
differentiator is Ambient Awareness.
