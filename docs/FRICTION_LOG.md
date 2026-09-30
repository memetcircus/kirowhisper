
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

### F18 — Interaction-model generation silently fell back to template utterances on a Bedrock daily-token cap
- **Task:** After adding new MCP tools, regenerate the Alexa interaction model so
  natural phrasings ("tell me about that session", "approve all the safe ones") map
  to the new intents.
- **Steps:** `npm run generate` (the bridge's generator scans `tools/list` and asks a
  Bedrock model to invent varied sample utterances per tool), then inspected the
  generated `en-US.json`.
- **Expected:** Rich, human sample utterances per new intent, as we'd seen on earlier runs.
- **Actual:** Every intent logged `template utterances used (Too many tokens per day,
  please wait before trying again.)` — the generator hit a Bedrock **daily** token
  quota and quietly degraded to generic templates like "describe session", "describe
  session please". So `DescribeSessionIntent` had no "tell me about that session" and
  `ApproveAllSafeIntent` had no "approve all the safe ones" — the exact natural phrases
  a user actually says were missing, and voice recognition would miss them.
- **Severity:** Medium (the tool ships, but is hard to invoke by natural voice; easy to
  miss because generation "succeeded").
- **Workaround:** Author the natural phrasings by hand in
  `skill-package/overrides/<locale>.utterances.json` (keyed by intent name) — the
  generator merges overrides locally with no model call, so it's immune to the token
  cap. Re-ran `npm run generate`; the overrides landed (e.g. `DescribeSessionIntent`
  went to 17 utterances) and the natural phrases were recognized live.
- **Suggestion:** Fail loudly (non-zero exit or a prominent summary line) when the LLM
  utterance step is skipped due to quota, so a degraded model isn't shipped silently;
  and let the generator fall back to a cheaper model or cache prior utterances.

### F19 — Read-only replies closed the voice session, breaking natural follow-ups
- **Task:** Let a supervisor ask several things in a row by voice — "get status" then
  "tell me about that session" then "which task failed" — without reopening the skill.
- **Steps:** Each read-only tool (`get_status`, `check_task_health`, `describe_session`)
  returned a plain informative sentence ("... the crew has two active sessions.").
- **Expected:** The mic stays open so the next question reaches the skill.
- **Actual:** The bridge decides `shouldEndSession` from whether the reply ends in "?"
  (`endsWithQuestion`, see F15). A statement-ending reply closed the session, so the
  follow-up ("tell me about that session") went to Alexa+ instead of the skill and
  came back as a platform error ("having trouble accessing your skill"). Every question
  needed a fresh "open kiro whisper" — the opposite of a fluid oversight conversation.
- **Severity:** Medium (each read-only answer worked, but the conversation couldn't continue).
- **Workaround:** A `keep_open()` helper appends a short "Anything else you'd like to
  check?" to a read-only reply when it doesn't already end in a question (so replies
  that already ask something, like the status digest's "Do you want to hear it?", are
  untouched). Server-side text only — the tool list didn't change, so a server restart
  sufficed (no runtime recreate, cf. F17). Verified live: status → describe → health ran
  back-to-back in one open session.
- **Suggestion:** Same as F15 — a first-class "expects a follow-up / keep the mic open"
  flag on a tool result would be far more robust than inferring it from a trailing "?".

### F20 — Two tools reported different session counts for the same crew
- **Task:** Answer "how many sessions" consistently across tools, so a voice user isn't
  told two different numbers seconds apart.
- **Steps:** Asked "get status" (which read the Gateway's `/api/status` `sessions`
  field) then "tell me about that session" and "which task failed" (which count slots
  from `/api/chat/slots`).
- **Expected:** One consistent count.
- **Actual:** "get status" said "**one** active session" while the other two said
  "**two** sessions total." Both were internally correct — `/api/status.sessions`
  counts only currently-*running* sessions, while the slot list includes finished ones —
  but to a user they simply contradict each other, which erodes trust in an oversight tool.
- **Severity:** Low (each number is defensible; the inconsistency is the problem).
- **Workaround:** `get_status` now counts the same real (non-empty) slots the other
  tools use, so all three agree; it falls back to the Gateway's `sessions` number only
  if the slot list can't be fetched. Verified live: "get status" and "tell me about that
  session" both say two.
- **Suggestion:** A single documented "session count" semantic (running vs. total, and
  which endpoint is canonical) would prevent clients from mixing two sources.

---

### F21 — On a real Echo, the model rewrote our confirm question into a statement and dropped the "yes"
- **Task:** The safety-critical moment — two-step approval by voice on a physical Echo
  Dot Max: "approve it" → "are you sure?" → "yes" → applied.
- **Steps:** Ran the full flow on-device. `approve_top`'s first call returned a summary
  plus a confirming question ending in "?" (verified server-side: "…To confirm, are you
  sure you want to approve this?").
- **Expected:** The "?" keeps the mic open (endsWithQuestion, see F15), the user says
  "yes", the second `approve_top` applies it.
- **Actual:** Alexa+ **paraphrased our whole reply** into a period-ending command — the
  device spoke "…please say yes to go ahead." (no "?"), so the bridge closed the session
  and the user's "yes" went to Alexa+, not the skill; nothing applied. This is F15
  recurring, but worse: even a reply that *did* end in "?" got reworded once we also
  handed the model a long summary sentence to read. The decision correctly stayed
  "Needs approval" (safety held — a single "approve it" never applied it), but the user
  could not complete the approval.
- **Severity:** High (the product's core safety action was uncompletable by voice on the
  real device).
- **Workaround:** Stop giving the model anything to rewrite on the confirm turn. The
  user already heard *what* the decision is (from `get_pending_decisions`/`explain_top`),
  so the confirm turn no longer repeats the summary — it is now a single bare yes/no
  question ("Say yes to approve it, or no to keep it waiting?"), and the tool description
  tells the model to speak it verbatim. Verified live on the Echo Dot Max: "approve it"
  → the bare question kept the mic open → "yes" reached the skill → the file was actually
  deleted (confirmed in the audit log as `user approved (voice, top)` and by the file
  being gone).
- **Suggestion:** Same as F15 — a first-class "this reply expects an answer, keep the
  session open" signal on a tool result would end this whole class of bug. Inferring it
  from a trailing "?" fails the moment a generative voice layer rephrases the text.

### F22 — No polite way to end the session ("thank you" doesn't close it)
- **Task:** End the conversation naturally on the device after finishing.
- **Steps:** Said "thank you" to close; then, because the mic stays open (every read-only
  reply ends in a question by design, F19), the assistant treated it as a new turn and
  kept going. Said "stop" instead.
- **Expected:** A natural "thanks, that's all" ends the session.
- **Actual:** "thank you" is not a built-in intent and our replies keep the mic open, so
  it looped. **"stop" worked cleanly** ("Okay, goodbye" → session closed) via Alexa's
  built-in `AMAZON.StopIntent`, which the bridge handles.
- **Severity:** Low (a standard exit exists; only the polite phrasing is unhandled).
- **Workaround / decision:** Left as-is by choice. "stop"/"cancel"/"exit" are the
  platform-standard ways to end a skill and they work; adding a bespoke "thank you =
  goodbye" intent would cost a new tool + the F17 four-step deploy and risks
  false-closing mid-sentence ("thank you, now approve it"). Not worth it against a
  feature freeze. Documented as a conscious product decision.
- **Suggestion:** A lightweight, built-in "polite close" set (thanks / that's all /
  never mind) that the platform maps to StopIntent would make voice skills feel more
  natural without each skill re-implementing it.

---

## Severity tally
- High: F1, F2, F8, F11, F12, F13, F14, F15, F17, F21
- Medium: F3, F4, F5, F7, F9, F10, F18, F19
- Low: F6, F16, F20, F22

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
agent until that session is actually torn down. F18–F20 came from a second round of
adding voice tools (`explain_top`, `check_task_health`, `describe_session`) and are the
"last mile" of shipping a voice feature: the intent must be *generatable* into the model
(F18 — a silent quota fallback dropped the natural phrasings), the reply must *keep the
conversation open* (F19 — statement-ending replies closed the session), and multiple
tools must *agree on the facts* (F20 — two session counts from two endpoints). None were
capability gaps; each was a seam between the deterministic server and the model-driven
voice surface, and each fix pushed correctness back to the source. F21–F22 are the
"last mile" again, this time surfaced only by testing on a **physical Echo Dot Max**:
the generative voice layer rewrote our safety-critical confirm question into a statement
and swallowed the user's "yes" (F21 — fixed by leaving the model nothing to reword), and
there is no polite spoken close, only the platform's "stop" (F22 — left as a conscious
decision). The throughline across F13–F22: the moment a generative model sits between
your tool and the speaker, never trust it to preserve wording, keep a turn open, or
relay a value — make the safety-critical behavior deterministic and verify the real
effect at the source. The whole flow, including the two-step approval, was ultimately
verified end-to-end on a real Echo Dot Max, with the deletion confirmed in the audit log.
