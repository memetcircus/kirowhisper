# Requirements — KiroWhisper

## Introduction

KiroWhisper is a layer that lets you **oversee the autonomous Kiro Crew by voice,
without looking at a screen**. On one side it talks to Alexa+ (or a simulated
voice interface); on the other it calls the Kiro Crew Gateway REST API. It is
packaged as a Model Context Protocol (MCP) server (spec 2025-11-25, Streamable HTTP).

The distinguishing capability is **Ambient Awareness**: it continuously watches
the dozens of approval requests Crew raises, classifies each by risk, silently
approves the low-risk ones, silently blocks the clearly dangerous ones, and
surfaces by voice **only the ones that genuinely need a human decision**. This
makes voice oversight *usable* for blind developers (voice cannot be scanned
serially like a screen; without a filter, voice approval becomes torture) and a
comfort for anyone away from the screen (the curb-cut effect).

**Actor:** Deniz — a blind, home-office developer (primary persona); curb-cut
expansion: any developer away from the screen/desk.

**Scope boundary:** KiroWhisper is an OVERSIGHT layer (monitor + approve), NOT a
voice coding tool. Starting new tasks is out of scope (v2).

**Feasibility:** The Crew side of the requirements below was verified with a live
spike (see the private working notes and `spike/`). The Crew Gateway REST
endpoints, auth (`?token=` + `Origin`), and programmatic approval
(`POST /api/chat/slots/<slot>/approve {action:"approved"}`) are proven working.

### Terminology
- **Gateway:** Kiro Crew's local REST/WebSocket server (`http://localhost:5476`).
- **Approval:** the point where Crew pauses before running a tool and waits for a
  human decision. Raw data: tool title, purpose, input (diff), `is_read_only`, `is_shell`.
- **Risk level:** LOW (reversible/read-only), HIGH (irreversible/destructive),
  UNKNOWN (cannot be safely determined).
- **Voice interface:** since the Alexa+ MCP add-on is not publicly available, a
  rules-compliant **simulated Alexa+ experience** (the user's own voice + STT + TTS).

---

## Requirement 1 — Ambient Awareness: continuously watch approval requests

**User Story:** As a developer, I want all approval requests Crew raises to be
watched continuously in the background, so that I never miss a decision and they
do not each interrupt me one by one.

#### Acceptance Criteria
1. WHEN one or more pending approvals exist on the Crew Gateway THEN the system SHALL detect all of them by periodic polling.
2. WHEN an approval request is detected THEN the system SHALL read its raw data (tool title, purpose, input/diff, `is_read_only`, `is_shell`).
3. WHILE Crew is running THE system SHALL keep watching without interruption and evaluate new requests as they appear.
4. IF the Gateway is unreachable (connection error) THEN the system SHALL retry silently and SHALL NOT treat any approval as auto-passed.

## Requirement 2 — Risk classification (the intelligence of Ambient Awareness)

**User Story:** As a developer, I want each approval classified by risk, so that
safe work does not disturb me, dangerous work is stopped, and only real decisions reach me.

#### Acceptance Criteria
1. WHEN an approval request is evaluated THEN the system SHALL assign it a risk level of LOW, HIGH, or UNKNOWN.
2. WHERE a request is read-only (`is_read_only`) or a clearly reversible edit THE system SHALL classify it as LOW.
3. WHERE a request involves a destructive/irreversible operation (e.g. deleting files/dirs, `rm -rf`, force push, touching prod) or a shell command (`is_shell`) THE system SHALL classify it as at least HIGH.
4. WHERE a request appears to expose a credential/secret (e.g. writing a key to a log) THE system SHALL classify it as HIGH.
5. IF the system cannot safely determine the risk of a request THEN the system SHALL classify it as UNKNOWN (never default to LOW).
6. WHEN raw diff/tool data is summarized for classification THEN the system SHALL use a language model (Amazon Bedrock) to produce a voice-friendly, decision-oriented summary.

## Requirement 3 — Filtering decision (three buckets)

**User Story:** As a developer, I want classified requests handled automatically
by risk, so that only genuine decisions reach me.

#### Acceptance Criteria
1. WHEN a request is classified LOW AND the user has granted trust for this kind of work in this session (or the default trust policy allows it) THEN the system SHALL auto-approve it (`action:"approved"`) and not disturb the user.
2. WHEN a request is classified HIGH AND is clearly destructive/dangerous THEN the system SHALL surface it to the user (never silently approve); silently blocking a request happens ONLY when it matches an explicit deny rule.
3. WHEN a request is classified UNKNOWN THEN the system SHALL ALWAYS surface it to the user (conservative default).
4. WHEN the system silently handles a request (pass or block) THEN the system SHALL write the decision to the audit log.
5. IF no trust policy or classification can be safely applied THEN the system SHALL surface the request to the user (fail-safe).

## Requirement 4 — Status query (PULL / summary)  [UC-1, UC-10]

**User Story:** As a developer, I want to ask "what's Kiro up to?" so that I get a
concise spoken status summary without looking at a screen.

#### Acceptance Criteria
1. WHEN the user asks for status THEN the system SHALL fetch Crew's overall state plus pending approvals and produce a voice-friendly summary.
2. WHERE there are multiple tasks/approvals THE summary SHALL include how many finished, how many are pending, and how many failed (standup summary).
3. WHEN Ambient Awareness has silently handled some requests THEN the summary SHALL also state how many were auto-passed and how many were blocked (e.g. "I passed 19, blocked 3, and 1 is waiting for you").
4. WHEN a summary is produced THEN it SHALL be expressed in decision-oriented language, not raw logs/diffs (voice-friendliness).

## Requirement 5 — Approving (double-confirm for high risk)  [UC-2]

**User Story:** As a developer, I want to approve a surfaced request by voice, and
be protected from misrecognition when it is destructive.

#### Acceptance Criteria
1. WHEN an approval request is surfaced to the user THEN the system SHALL explain by voice what it does (summary + risk).
2. WHERE the request is HIGH risk (destructive/irreversible) THE system SHALL re-confirm intent before approving (e.g. "this deletes 42 lines and cannot be undone, are you sure?") and SHALL accept ONLY a clear affirmative ("yes", "I approve").
3. WHEN the user approves a request THEN the system SHALL send the approval to Crew (`POST /api/chat/slots/<slot>/approve` with body `{"action":"approved","request_id":<id>}`).
4. IF sending the approval fails THEN the system SHALL inform the user and treat the request as unresolved (must not falsely say "approved").
5. WHERE speech recognition confidence is low or the answer is ambiguous THE system SHALL re-ask rather than approve a destructive operation.

## Requirement 6 — Rejecting and sub-options  [UC-3]

**User Story:** As a developer, I want control over what happens when I say "no",
so that no wrong action occurs.

#### Acceptance Criteria
1. WHEN the user rejects a request THEN the system SHALL first reassure that the operation was not performed ("I didn't do it").
2. WHEN after a rejection THEN the system SHALL offer three options in a fixed order with clear verbs: SKIP / PAUSE / CANCEL.
3. WHERE the user chooses SKIP THE system SHALL reject that step and let the task continue (`action:"rejected"`).
4. WHERE the user chooses PAUSE THE system SHALL pause the task and not advance it until a new instruction arrives.
5. WHERE the user chooses CANCEL THE system SHALL request an extra confirmation (because it is destructive) and then stop the task entirely.
6. IF the user gives an ambiguous answer after rejection, or does not answer (timeout) THEN the system SHALL fall back to the safest option (PAUSE).

## Requirement 7 — Proactive notification (the colleague calls you)  [UC-5]

**User Story:** As a developer, I want KiroWhisper to speak up on its own when a
real decision is needed while I am away from the screen, so that I don't have to
keep asking.

#### Acceptance Criteria
1. WHEN a request passes the Ambient Awareness filter and must be surfaced THEN the system SHALL produce a proactive spoken/audible alert.
2. WHEN a proactive alert is triggered THEN it SHALL be only for requests that genuinely need a decision (no alert for LOW/silently-handled ones).
3. WHERE native Alexa+ proactive speech is not possible THE system SHALL realize it via simulation/staging and SHALL disclose this honestly in the demo (no misleading presentation).
4. WHEN a task fails THEN the system SHALL report it (proactively or when the user next asks).

## Requirement 8 — Session trust ("always approve from now on")  [UC-6]

**User Story:** As a developer, I don't want to be asked repeatedly for a task I
trust; I want to opt into auto-approving the remaining low-risk steps.

#### Acceptance Criteria
1. WHEN the user grants trust for a session/task THEN the system SHALL auto-approve the remaining LOW-risk steps in that scope (`action:"trust"`).
2. WHERE a step carries HIGH or UNKNOWN risk THE system SHALL still surface it despite session trust (trust does not override safety).
3. WHEN session trust is enabled THEN the system SHALL clearly tell the user and state what it covers.

## Requirement 9 — Context tracking  [UC-7, UC-9]

**User Story:** As a developer, I want the system to track which of several tasks
I'm referring to, and to be able to ask me open-ended questions when needed.

#### Acceptance Criteria
1. WHERE there are multiple active tasks/approvals THE system SHALL map the user's references ("open the failing one", "approve the second") to the correct task.
2. WHEN Crew is waiting for an open-ended choice (`waiting_for_input`/`has_options`) THEN the system SHALL present the options by voice and relay the user's choice.
3. WHEN decisions are made across a session THEN the system SHALL retain near-context (last-referenced task, etc.) to support follow-up questions.

## Requirement 10 — Audit log  [UC-11]

**User Story:** As a system owner, I want all approve/reject/filter decisions
recorded, so that security and accountability are ensured.

#### Acceptance Criteria
1. WHEN the system makes a decision (approve/reject/auto-pass/auto-block) THEN it SHALL be recorded with a timestamp, request id, risk level, and decision.
2. WHEN the user asks THEN the system SHALL be able to summarize past decisions by voice (e.g. "I blocked 3 dangerous operations today").
3. WHEN a destructive operation is approved/rejected THEN the record SHALL persist that decision.

## Requirement 11 — Voice interface and simulation  [general]

**User Story:** As a developer, I want to talk to the system with my own voice,
and I want it to work even without access to real Alexa+ deployment.

#### Acceptance Criteria
1. WHEN the user issues a voice command THEN the system SHALL transcribe speech to text (STT) and produce the response as speech (low-latency TTS).
2. WHERE there is no access to a real Alexa+ MCP add-on THE system SHALL provide a rules-compliant simulated Alexa+ experience; the backend (MCP + Crew + Bedrock) SHALL be entirely real, only the Alexa+ interaction layer simulated.
3. WHEN the system produces an approval/summary THEN the response SHALL be voice-appropriate in length and clarity (not screen text).
4. WHERE the demo is presented THE simulation SHALL be disclosed honestly (no misleading presentation as if connected to real Alexa+).

## Requirement 12 — MCP server packaging

**User Story:** As a hackathon entrant, I want KiroWhisper's core packaged as a
real MCP server, so that it satisfies the Alexa+ track's runtime-technology requirement.

#### Acceptance Criteria
1. WHEN KiroWhisper's core capabilities are exposed THEN they SHALL be surfaced as MCP tools (spec 2025-11-25, Streamable HTTP), e.g. get_status, get_pending_decisions, approve, reject, summarize.
2. WHEN the MCP server receives a tool call THEN it SHALL make the corresponding Crew Gateway REST call and return the result as an MCP response — i.e. MCP technology is genuinely invoked at runtime (not merely named in the README).
3. WHERE the code repository is submitted THE MCP server source and run instructions SHALL be included.

---

## Non-Functional Requirements

### NFR-1 — Security (fail-safe)
- No request whose risk is uncertain is ever silently approved (conservative default).
- Destructive operations are handled only via explicit user approval or an explicit deny rule.
- Secret/token values are never echoed back in voice responses.

### NFR-2 — Latency (demo fluidity)
- Spoken feedback after a decision must be low-latency; no long silences that
  break the approval flow (TTS speed over polish).

### NFR-3 — Voice-friendliness
- All output is fit for auditory consumption: short, priority-ordered, not raw diff/log.
- At most 2-3 options are presented by voice at once (the ear's limit).

### NFR-4 — Accessibility
- Full eyes-free functionality: no critical flow depends on seeing a screen.
- Consistency: options always in the same order/words (learnability).

### NFR-5 — Hackathon compliance
- Repo is public + open-source licensed (visible LICENSE).
- <3 min demo video; simulation honestly labeled.
- Product Feedback for each tool/SDK; a Friction Log is kept (bonus).

---

## Priority (scope)
- **CORE:** R1, R2, R3 (Ambient Awareness) + R4, R5, R6, R7, R11, R12 + NFR-1..5
- **DIFFERENTIATOR:** R8, R9, R10
- **FUTURE (v2):** mid-task redirect (UC-8), voice-starting new tasks

## Traceability (use case -> requirement)
- Ambient Awareness -> R1, R2, R3
- UC-1/UC-10 -> R4 | UC-2 -> R5 | UC-3 -> R6 | UC-4/UC-12 -> R4/R7
- UC-5 -> R7 | UC-6 -> R8 | UC-7/UC-9 -> R9 | UC-11 -> R10
- All UC -> R11 (voice), R12 (MCP packaging)
