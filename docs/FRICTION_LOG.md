# Friction Log

Specific frictions hit while building KiroWhisper, kept as we went. Each entry:
task attempted · steps · expected vs actual · severity · workaround · suggestion.

---

### F1 — Authenticating to the Crew Gateway from our own code
- **Task:** Call `GET /api/status` on the local Gateway from a Python client.
- **Steps:** Read the Gateway secret from `~/.kiro/crew/run/gateway-5476.secret`; sent
  it as a `Cookie: mc_token=…`, then as `Authorization: Bearer …`, then `X-Gateway-Secret`.
- **Expected:** One of the standard auth schemes returns `200`.
- **Actual:** Every attempt returned `{"error":"Token required","code":"forbidden"}`.
  The real scheme is a signed token from `kirocrew token`, passed as a `?token=`
  **query parameter**, **plus** an `Origin` header equal to the base URL.
- **Severity:** High (blocked all progress until solved).
- **Workaround:** Fetch the token via `kirocrew token`, send it as a query param, and
  always set `Origin: http://localhost:5476`.
- **Suggestion:** Document "connecting a third-party client" with the exact auth shape,
  or accept a standard `Authorization: Bearer` header.

### F2 — The approve action string silently rejects
- **Task:** Programmatically approve a pending tool call.
- **Steps:** `POST /api/chat/slots/<slot>/approve` with `{"action":"approve","request_id":…}`.
- **Expected:** The tool runs (file gets created).
- **Actual:** Response was `{"ok": true}`, but the agent reported the tool was **denied**.
  The endpoint only treats `action:"approved"` (past tense) as approval; anything else
  falls through to "rejected".
- **Severity:** High (looks successful, silently does the opposite).
- **Workaround:** Always send `action:"approved"`. We locked this into a constant and a
  regression test.
- **Suggestion:** Return a validation error for unrecognized actions, or accept both
  `"approve"` and `"approved"`.

### F3 — `kirocrew-client` cookie auth + not on PyPI
- **Task:** Reuse the official Python client instead of writing our own.
- **Steps:** `pip install kirocrew-client` (fails — not published); installed from the
  repo subdirectory; it authenticates via a `mc_token` cookie.
- **Expected:** A working client.
- **Actual:** Not on PyPI, and its cookie auth was rejected by our running Gateway (see F1).
- **Severity:** Medium.
- **Workaround:** Wrote a ~200-line REST client (`gateway_client.py`) using the
  query-param + Origin scheme.
- **Suggestion:** Publish the client and align its auth with the running Gateway.

### F4 — MCP SDK 2.x renamed FastMCP with no runtime shim
- **Task:** Build an MCP server over Streamable HTTP.
- **Steps:** `from mcp.server.fastmcp import FastMCP` (from every tutorial).
- **Expected:** Import works.
- **Actual:** `ModuleNotFoundError` — `mcp` 2.x renamed `FastMCP` to `MCPServer`
  (`mcp.server.mcpserver`). The error message did link a migration guide (nice), but
  all example code breaks.
- **Severity:** Medium.
- **Workaround:** Used `MCPServer`; introspected `inspect.signature` for the current API.
- **Suggestion:** Put a prominent 1.x→2.x note (and a `mcp<2` pin option) at the top of
  the getting-started docs.

### F5 — Pending approvals not where expected on the slot
- **Task:** Read the currently pending approval for a slot.
- **Steps:** Checked the slot object's `pending_approval` / `pending_approval_info`.
- **Expected:** Populated when a tool is awaiting approval.
- **Actual:** Those fields stayed null; the reliable signal was a message with
  `role:"permission"` carrying `meta.approval_id` (and the useful `tool_input`,
  `is_read_only`, `is_shell`).
- **Severity:** Medium.
- **Workaround:** Parse the latest `role:"permission"` message from the slot's messages.
- **Suggestion:** Populate `pending_approval` consistently, or document the permission-
  message shape as the canonical source.

### F6 — Deny-on-silence timing during testing
- **Task:** Approve a tool call programmatically end-to-end.
- **Steps:** Fire a task, poll for the approval, then approve it.
- **Expected:** Approve whenever we get to it.
- **Actual:** Unresolved approvals time out to a safe *reject* after ~60–75s
  ("deny on silence"). Approving after that window has no effect.
- **Severity:** Low (and it's good, safe behavior).
- **Workaround:** Poll at ~1s and approve within the window; documented the timing.
- **Suggestion:** Expose the timeout value via the API so clients can display/anticipate it.

### F7 — Proactive voice is not native to the MCP/Alexa+ path
- **Task:** Have the assistant speak up on its own when a real decision appears.
- **Steps:** Looked for a server-initiated push in the MCP/Alexa+ request-response model.
- **Expected:** A way for the server to initiate speech.
- **Actual:** MCP is request-response; the server can't spontaneously talk, and Alexa+
  proactive speech isn't available via add-ons today (confirmed by the Alexa+ team on
  the hackathon forum — but demoing it in a submission is allowed).
- **Severity:** Medium (it's the emotional core of the "colleague calls you" story).
- **Workaround:** The Ambient engine pushes surfaced decisions to the web UI over SSE,
  which speaks the proactive alert — a rules-compliant simulation, honestly labeled.
- **Suggestion:** A proactive/notification channel for add-ons would unlock this class
  of "ambient assistant" experiences.

### F8 — Browser `speechSynthesis` produced no audio, silently
- **Task:** Speak the assistant's replies aloud in the browser (TTS).
- **Steps:** Called `speechSynthesis.speak(new SpeechSynthesisUtterance(text))` after a
  user gesture; confirmed `getVoices()` returned 199 voices; tried `cancel()` first,
  set `lang`/`rate`, listened for `onend`/`onerror`.
- **Expected:** Audible speech, or at least an `onerror` when it can't play.
- **Actual:** No audio at all on a Chrome/macOS setup — and no error fired, so the app
  had no signal that anything failed. "Spoke" and "silently did nothing" are
  indistinguishable.
- **Severity:** High (broke the entire voice-output half of the demo).
- **Workaround:** Moved TTS server-side to the host's own `say` via a `/api/speak`
  endpoint, and disabled browser speech entirely so it can never fire. Instantly reliable.
- **Suggestion:** Surface a real failure (throw, or fire `onerror`) when synthesis can't
  produce audio, so apps can fall back deterministically.

### F9 — Hands-free STT hears its own TTS (feedback loop)
- **Task:** Keep the mic open for continuous, hands-free commands while also speaking replies.
- **Steps:** `SpeechRecognition` with `continuous = true`, auto-restarting on `onend`,
  speaking replies through TTS while the session stayed "listening."
- **Expected:** The system hears the user, not itself.
- **Actual:** TTS output was captured as a new "command" (e.g. our own words matched
  "no"/"reject"), which triggered another reply, which was heard again — an endless
  loop. Separately, multiple open tabs each spoke at once, so voices overlapped.
- **Severity:** Medium.
- **Workaround:** Ignore recognition results while speaking, add a short cooldown after
  speech before re-opening the mic, dedup identical phrases, and serialize server-side
  TTS so only one voice plays at a time. Headphones remove the acoustic path entirely.
- **Suggestion:** A built-in "suppress self-audio while speaking" (echo/barge-in
  handling) would make hands-free voice UIs far easier to build correctly.

### F10 — Stale tool count leaked from a long-lived voice session
- **Task:** Report the number of pending decisions by voice ("N decisions are waiting").
- **Steps:** Ran the real Alexa+ path through the MCP bridge, whose agent keeps one
  long-lived conversation per user. Asked "what needs my decision" repeatedly as the
  real count changed.
- **Expected:** The spoken count always matches the current pending count.
- **Actual:** The number drifted (e.g. a stale "six decisions waiting" when only one
  was real), even after the backend and the tool both agreed on the true count. The
  agent was paraphrasing a number it had *said in an earlier turn* rather than reading
  this turn's fresh tool result — the count lived inside a prose sentence, which the
  model treats as reworkable text.
- **Severity:** Medium (wrong, alarming numbers erode trust in an oversight tool).
- **Workaround:** First returned the count as a structured field (`pending_count`) plus
  a prompt rule that a fresh number overrides earlier ones. **This was later reversed —
  see F14:** returning `structuredContent` made the bridge drop the spoken text, so the
  final fix was plain text (`structured_output=False`) with the count in the sentence,
  and a source-level fix (ghost-entry cleanup in the ambient engine) that keeps the
  count correct regardless.
- **Suggestion:** For voice, the real fix was upstream — keep the pending set correct at
  the source rather than trusting the model to relay a number.

### F11 — MCP session died between turns on a tunnelled SSE stream
- **Task:** Serve the MCP server to a long-lived agent (Alexa+ via the bridge) through
  a public tunnel, with minutes of idle time between voice turns.
- **Steps:** Default Streamable HTTP (SSE mode) behind a cloudflared quick tunnel; the
  bridge holds one MCP client per user across turns.
- **Expected:** A tool call after an idle gap just works.
- **Actual:** The next call failed with JSON-RPC `-32600 "Session not found"`. The
  tunnel drops idle SSE streams, so the server-side session expired, but the client
  still held the old session id and the transport's `onclose` never fired (a non-2xx
  POST doesn't close the transport), so it never reconnected on its own.
- **Severity:** High (broke the first voice turn after any pause).
- **Workaround:** Two layers. (1) Run the MCP server **stateless** (`stateless_http`,
  `json_response`) — with no server-side session, "Session not found" is impossible.
  Elicitation was already removed from the voice flow, so the SSE back-channel wasn't
  needed. (2) In the bridge, detect exactly this error, drop the dead client, and retry
  the call once on a fresh connection.
- **Suggestion:** Document that idle SSE streams behind tunnels expire sessions, and
  recommend stateless mode for stateless tool surfaces.

### Design note — slot deletion is deliberately kept off the voice/MCP surface
- **Context:** Our test scripts create throwaway chat slots, which pile up in Crew's
  UI. It's tempting to add a `delete_slot` to the Gateway client (or an MCP tool) to
  clean them up.
- **Decision:** We don't. Deleting a slot is destructive and irreversible — it discards
  the slot's whole conversation history and any task context. On a voice surface, one
  misheard word could wipe real work, which is the exact opposite of KiroWhisper's
  promise (protect the risky, fail safe). Note also that an **expired approval is not
  the same as a deletable slot**: deny-on-silence already resolved the *decision*
  safely, but the slot still holds its history.
- **Resolution:** Slot deletion exists only as an explicit developer tool
  (`scripts/cleanup_test_slots.py`), guarded to touch only known test-prefixed slots,
  with a `--dry-run`. It is never reachable from the product.

### F12 — High-risk voice approval had no second confirmation
- **Task:** Approve the top pending decision by voice for an eyes-free user.
- **Steps:** The Alexa-reliable path is a two-call flow: `get_pending_decisions`, then
  `approve_top`/`reject_top` (no request id, no elicitation round trip). A single "yes"
  reached `approve_top`.
- **Expected:** A destructive, irreversible step (a shell `rm`) needs an explicit second
  confirmation — the product's whole promise is protecting the risky ones.
- **Actual:** `approve_top` resolved a HIGH-risk decision on the first "yes" with no
  re-confirmation (the low-level `approve` had a `confirmed` flag, but the voice path
  bypassed it). Separately, resolving an approval that had already expired still returned
  `{"ok": true}`, so the tool falsely reported success.
- **Severity:** High (a safety guarantee, silently missing on the primary voice path).
- **Workaround:** `approve_top` now arms a short-lived, request-id-bound confirmation:
  the first call on a HIGH-risk decision only asks "are you sure?"; a second call within
  the window applies it. And resolve verifies the exact permission's real `meta.resolved`
  state instead of trusting `{"ok": true}`, raising a distinct "not pending" error on
  expiry so nothing is reported as approved when it wasn't.
- **Suggestion:** Bake a "requires confirmation" attribute into the approval model so
  every client enforces it consistently.

### F13 — Alexa+ sometimes answers instead of routing to the skill
- **Task:** Say a natural request ("what needs my decision") inside an open skill
  session and have it reach our skill.
- **Steps:** Opened the skill, then spoke intents; inspected CloudWatch to see whether
  the Lambda was actually invoked.
- **Expected:** While the skill session is open, utterances go to the skill.
- **Actual:** Some phrasings were answered by Alexa+'s own general assistant and never
  reached our Lambda at all (no invocation logged), producing plausible but fabricated
  replies with zero backend effect. It was intermittent and depended on wording.
- **Severity:** High (silent: the user hears a confident answer that did nothing).
- **Workaround:** Prefer the explicit "ask &lt;skill&gt; …" launch form, which routed
  reliably; and always verify real effect against the backend, never trust the spoken
  reply alone. We also learned to compare a direct MCP call with the bridge turn to tell
  "Alexa answered" from "the tool ran."
- **Suggestion:** A clearer contract for when an open skill session keeps the turn vs.
  when the platform reclaims it would make skill behavior predictable.

### F14 — A `-> str` MCP tool still advertises an output schema, which broke voice
- **Task:** Return a spoken sentence from a tool and have the agent read it aloud.
- **Steps:** Tool typed `-> str`; the Python MCP SDK auto-detected structured output and
  advertised an `outputSchema` (`{"result": string}`) plus `structuredContent`.
- **Expected:** A plain string is spoken as-is.
- **Actual:** Two failures. (1) The bridge sends the model a single block and, when
  `structuredContent` is present, drops the text — so the model treated the sentence as
  data to summarize and skipped reading the decision aloud (unusable for an eyes-free
  user). (2) After we changed the shape, a warm agent had cached the old schema and the
  SDK rejected the new result with `-32600/-32602 "... output schema ..."`.
- **Severity:** High (the decision content — the whole point — wasn't spoken).
- **Workaround:** Set `structured_output=False` so the tool returns one plain-text block
  (words to speak, no schema to drift). Also taught the bridge client to treat a
  stale-schema error like a stale session: drop the client and reconnect once, which
  re-lists tools against the current schema.
- **Suggestion:** Make it obvious that a `-> str` return still opts into structured
  output, and document how a client should behave when a server's schema changes.

### F15 — Confirmation turn closed the session because the reply wasn't a question
- **Task:** Two-step voice approval: after "approve it", ask "are you sure?", then apply
  on the user's "yes".
- **Steps:** The confirm tool returned a prompt; the bridge decides `shouldEndSession`
  from whether the spoken reply ends in "?" (`endsWithQuestion`).
- **Expected:** The confirm prompt keeps the mic open so the user's "yes" reaches the
  skill and the second call fires.
- **Actual:** The model rewrote our question ("...approve it?") into a period-ending
  command ("...to confirm you want this to run."). No "?" → the bridge closed the
  session → the confirming "yes" went to Alexa+, not the skill → the second call never
  fired and nothing applied (while Alexa+ said "approved" — see F13).
- **Severity:** High (the confirmed action silently didn't happen).
- **Workaround:** Made the confirm prompt one short, bare question the model is least
  likely to reword ("To confirm, are you sure you want to approve this?"), and made the
  tool description state plainly that approval takes two calls and the model must call
  again on confirmation. Verified live end-to-end: arm → "yes" reaches skill → second
  call fires → file actually deleted.
- **Suggestion:** A first-class "expects an answer / keep the mic open" signal from the
  tool result would be far more robust than inferring intent from a trailing "?".

---

### F16 — Crew's own agent refuses catastrophic commands before they reach an approval
- **Task:** Exercise KiroWhisper's AUTO_BLOCK bucket end to end — have Crew attempt a
  catastrophic shell command and watch our deny rule reject it silently.
- **Steps:** Sent slots asking Crew to run `mkfs.ext4 …` and `curl … | sh`, then
  watched the Gateway for the approval and our audit log for an auto-block.
- **Expected:** Crew raises an approval for the dangerous command; KiroWhisper's
  `is_catastrophic` rule auto-blocks it and records it, so "get status" can say
  "I blocked one dangerous one."
- **Actual:** The approval never appeared. Crew's own model declined to run the
  command itself ("I won't run that — `mkfs.ext4` formats a filesystem…"), so nothing
  was ever handed to KiroWhisper to block. The auto-block path is only reachable for
  commands Crew is willing to attempt but that match our rules — a narrower set than
  expected. Merely-risky commands (e.g. a scoped `rm -rf /tmp/x`) *do* come through and
  are surfaced correctly.
- **Severity:** Low (it's good, layered safety — Crew refuses the worst, we catch the
  rest — but it means a demo rarely shows a non-zero "blocked" count).
- **Workaround:** Keep `is_catastrophic` as a real, tested defense-in-depth layer, but
  don't headline a "blocked N dangerous ops" number in the demo; lead with the
  auto-pass and surface behaviors, which fire reliably. Documented the layering in the
  README so the block bucket isn't oversold.
- **Suggestion:** A Crew setting to route a policy-violating command to the approval
  channel (instead of the model refusing outright) would let an oversight tool own the
  block decision and log it, rather than the refusal happening invisibly upstream.

---

### F17 — A newly added MCP tool stayed invisible to the voice agent until the runtime was recreated
- **Task:** Add a new MCP tool (`check_task_health`) to the running server and reach it
  by voice ("which task failed") through the Alexa+ bridge.
- **Steps:** Added the tool server-side (verified live: `tools/list` over the tunnel
  showed all 11 tools, and a direct `tools/call` returned the correct answer). Then,
  in order: regenerated the Alexa interaction model and `ask deploy`'d it; redeployed
  the Lambda via CDK (`npm run deploy`); restarted the local MCP server; updated the
  AgentCore runtime env several times (cache-buster vars, `LOG_LEVEL=debug`); changed
  the public tunnel URL and redeployed; lowered `idleTimeoutMinutes` to 1 and waited
  past it; and even stopped the MCP server briefly to try to force a reconnect.
- **Expected:** After regenerating + deploying the model and manifest, the agent can
  call the new tool.
- **Actual:** The Alexa NLU recognized the new intent (`CheckTaskHealthIntent` reached
  the Lambda) and the Lambda correctly hinted `tool: check_task_health` to the runtime —
  but the **agent** kept replying "I don't have a tool to check task health." CloudWatch
  showed why: every turn logged `warmup … elapsedMs: 0` and there was **no**
  `mcp session ready` line, i.e. the agent never re-ran `listTools()`. The bridge fetches
  the MCP tool list once per warm agent session (`startWarmup` is idempotent; it only
  resets on a *failed* warmup), and that session had cached the pre-tool 8-tool list.
  The container hosting it lived on (`maxLifetimeHours: 8`) and kept serving the old
  cache; none of the redeploys, env updates, URL change, idle-timeout drop, or a brief
  server outage tore that warm session down. Tellingly, with the MCP server **stopped**
  the agent still answered normally from its cache instead of erroring — proof it wasn't
  re-listing tools at all.
- **Severity:** High (a shipped tool is completely unreachable by voice, with no error —
  the skill even *suggests* the command in its greeting, so it looks broken).
- **Workaround:** Recreate the runtime from scratch: `npm run destroy` (removes the
  AgentCore stack **and** the container image) then `npm run deploy` + `npm run
  skill:deploy`. The brand-new container had no warm session, so its first turn ran a
  fresh `listTools()` and picked up all 11 tools. Verified live: "check task health" →
  "One task failed with a command not found error, exit status 127. Two finished
  cleanly." Adding a tool therefore takes **four** steps, not one: (1) `npm run generate`,
  (2) `npm run skill:deploy`, (3) `npm run deploy`, and — because of the warm cache —
  (4) `npm run destroy && npm run deploy` (or otherwise guarantee a cold container).
- **Suggestion:** The bridge should re-list tools when a turn references a tool the
  current session doesn't know (or expose a way to invalidate the per-session tool
  cache), so a newly deployed tool becomes reachable without recreating the runtime.
  Documenting that the agent snapshots `tools/list` once per warm session — and that
  `update-agent-runtime` does not necessarily recycle a live container — would have
  saved hours.

---

## Severity tally
- High: F1, F2, F8, F11, F12, F13, F14, F15, F17
- Medium: F3, F4, F5, F7, F9, F10
- Low: F6, F16

Most frictions were about **discovery** (how to talk to the Gateway, which action
string, where the pending approval lives) rather than capability gaps — the
capabilities were all there. Better client docs would remove the majority of these.
The browser voice frictions (F8, F9) were the exception: real behavioral gaps in the
Web Speech API that only surface once you wire up genuine hands-free interaction, and
they pushed us to a more reliable host-TTS architecture. The later frictions (F10–F15)
came from the real Alexa+ device path via the MCP bridge, and they share a theme: a
long-lived, tunnelled, model-driven session behaves nothing like a short-lived local
call. Stale values (F10), dead sessions (F11), missing/lost confirmation (F12, F15),
the platform answering instead of the skill (F13), and schema-vs-plain-text output
(F14) only appeared once real speech drove a real agent. Each pushed a concrete fix,
and the recurring lesson was the same: never trust the spoken reply as proof — verify
the real effect at the source, and keep the safety-critical logic deterministic rather
than dependent on how the model phrases a turn. F16 is a different, welcome kind of
friction: Crew's own agent already refuses the most catastrophic commands, so our
auto-block layer is defense-in-depth we don't oversell rather than the star of the demo.
F17 was the costliest of all: a correctly shipped tool was invisible by voice because a
warm agent session caches `tools/list` once and the hosting container outlived every
redeploy — the fix was to recreate the runtime so a cold container re-lists the tools.
It reinforced the same theme from the other direction: the long-lived, model-driven
session is the hard part, and "deployed" at the server does not mean "visible" to the
agent until that session is actually torn down.
