# Product Feedback

Honest feedback on every tool, API, and SDK used to build KiroWhisper. Format per
tool: what we used it for · what worked · what needs work · onboarding · would we
build with it again.

---

## Kiro Crew (Gateway REST API)

**What we used it for.** The whole point of KiroWhisper: supervising an autonomous
Crew by voice. We drive the Gateway's REST API to read status and pending approvals
(`/api/status`, `/api/approvals`) and to resolve them
(`/api/chat/slots/<slot>/approve`).

**What worked well.** Crew's human-in-the-loop model is exactly the right primitive
for this — every consequential tool call already pauses for a decision, and
"deny on silence" (an unresolved approval times out to a safe reject) matches the
safety posture we wanted. The desktop app started a bundled Gateway with no fuss,
and `kirocrew token` gives a clean way to authenticate a local client.

**What needs work.**
- **Auth is undocumented for third-party clients.** It took real reverse-engineering
  to learn that the Gateway wants the token as a `?token=` **query parameter** (not
  a cookie or `Authorization` header) *and* an `Origin` header equal to the base URL,
  or it returns `403 Token required` / `Forbidden`. A short "talking to the Gateway
  from your own code" doc would save hours.
- **The approve action string is a silent trap.** The resolve endpoint accepts
  `action: "approved"` (past tense). Sending `"approve"` returns `{"ok": true}` but
  **silently rejects** the tool. A validation error, or accepting both, would prevent
  a very confusing failure mode.
- **The Python client (`kirocrew-client`) didn't work for us.** It authenticates via
  a `mc_token` cookie, which the running Gateway rejected; it also isn't on PyPI. We
  ended up writing a thin REST client instead. A working, published client would be great.
- Pending approvals were most reliably read from the slot's `role:"permission"`
  messages (with `meta.approval_id`), not the slot's `pending_approval` field, which
  stayed null in our runs. Documenting the canonical source would help.

**Onboarding (zero to hello world).** Installing and launching Crew was smooth. Going
from "it's running" to "my code can drive it" was the hard part — mostly the auth
details above.

**Would we build with it again?** Yes. Once the auth shape is known, the Gateway is a
powerful, well-behaved foundation, and the approval model is a genuinely good fit.

---

## Amazon Bedrock (Converse API, Nova Lite)

**What we used it for.** Nuanced risk classification of ambiguous tool calls, and
turning raw diffs/status into short, voice-friendly summaries.

**What worked well.** The **Converse API is model-agnostic** — the same call shape
works across Nova and Claude, so we could keep the model id in config and swap it
freely. Nova Lite is fast and cheap enough to sit in a polling loop. `us-east-1`
model access was straightforward once the account was set up.

**What needs work.** Structured/JSON output still needs defensive parsing — we clamp
to the first `{...}` and treat anything unparseable as UNKNOWN. A first-class
"strict JSON schema" mode on Converse would remove that boilerplate.

**Onboarding.** Enabling model access in the Bedrock console and calling `converse`
was quick. The AWS account/region setup was the longer part, not Bedrock itself.

**Would we build with it again?** Yes — the model-agnostic Converse call made the
"rules first, model only when unsure" design easy and cheap.

---

## MCP Python SDK (`mcp`, Streamable HTTP)

**What we used it for.** Packaging KiroWhisper's core as a real MCP server (the
Alexa+ track's runtime requirement), exposing tools like `get_status`, `approve`,
`reject`, `summarize` over Streamable HTTP.

**What worked well.** Once located, the high-level server API is clean: a `@tool`
decorator, and `run_streamable_http_async()` brings up a Streamable HTTP server with
almost no ceremony. `call_tool()` made the tools testable without a network client.

**What needs work.** We hit a **major-version rename with no runtime shim**: `mcp` 2.x
renamed `FastMCP` to `MCPServer` (`mcp.server.mcpserver`), so example code and older
tutorials fail with an import error. The error message did point to a migration
guide, which helped — but pinning guidance ("use `mcp<2` for v1 code") in the primary
docs would reduce surprise.

- **SSE vs stateless is a real deployment decision, not a detail.** The default
  Streamable HTTP mode keeps a server-side session with an SSE back-channel. Behind a
  tunnel with a long-lived client and minutes of idle time between calls, that session
  expires and the next call fails with `-32600 "Session not found"`. Since our voice
  flow makes no server→client requests (no elicitation), `stateless_http=True` with
  `json_response=True` removed the whole failure class — every call stands alone. A
  short "pick stateless unless you elicit" note in the docs would help.
- **Keep authoritative values in `structuredContent`, not just text.** A tool that
  returned its count inside a prose sentence let a long-lived agent paraphrase a stale
  number from an earlier turn. Moving the count into a real structured field (which the
  client treats as authoritative) fixed it. This is easy to do once you know the
  unstructured text and `structuredContent` are both sent and the client prefers the
  latter.

**Onboarding.** Fast, after resolving the 1.x-vs-2.x confusion. Introspecting the
installed package (`inspect.signature`) was the quickest way to get the current API.

**Would we build with it again?** Yes. Streamable HTTP support out of the box is
exactly what the Alexa+ track needs — and stateless mode made it robust behind a tunnel.

---

## Alexa+ via the MCP bridge (Bedrock AgentCore Runtime)

**What we used it for.** Driving the real Alexa+ / Echo path for KiroWhisper: an Alexa
Skill Lambda forwards each turn to an agent on Bedrock AgentCore Runtime, which calls
our MCP server's tools and speaks the results. We reached it through Kay Lerch's
open-source `alexa-skill-mcp-bridge` and exercised it end-to-end in the Alexa developer
console simulator against a real deployed runtime.

**What worked well.** The bridge is a faithful stand-in for a future Alexa+ MCP add-on:
tools are discovered from the live server, and the two-call voice flow
(`get_pending_decisions` → `approve_top`/`reject_top`) rides straight through to real
Crew approvals. Once wired up, decision-read, safe-reject, and a high-risk
two-step approve all worked by voice against the real backend.

**What needs work (platform behaviors we had to design around).**
- **One long-lived agent session per user.** AgentCore keys the session by a hash of
  the Alexa user id, so the same warm agent (with its rolling conversation history)
  serves every turn. That is what let a stale spoken count survive across turns — the
  fix belonged on our side (structured values), but the behavior is worth knowing.
- **Alexa+ sometimes answers instead of the skill.** Certain phrasings ("what needs my
  decision") were handled by Alexa's own general assistant and never reached our Lambda
  (confirmed by the absence of any Lambda invocation). Using the explicit
  "ask &lt;skill&gt; …" launch form routed reliably to the skill.
- **Deny-on-silence is unforgiving for a slow voice demo.** Crew expires an unresolved
  approval in ~60–75s (see Friction Log F6). Opening the skill and speaking often
  outran that window, so we ran a tiny helper that always keeps one fresh throwaway
  approval waiting during testing.

**Onboarding.** The bridge's own docs and CLI (`npm run chat --remote`) made it possible
to reproduce the deployed path locally, which was essential — the fastest way to tell
"the model hallucinated" from "the tool returned wrong data" was comparing a direct MCP
call with a bridge turn.

**Would we build with it again?** Yes. It's the closest thing to a real Alexa+ MCP
surface available today, and it proved the whole KiroWhisper concept on a physical Echo.

---

## Browser Web Speech API (STT + TTS)

**What we used it for.** The simulated Alexa+ voice surface: the user speaks (STT)
and the system replies aloud (TTS), all in the browser with zero dependencies.

**What worked well.** Zero install, low latency, and it kept the demo honest — it's
the user's *own* live voice in and a real-time voice out, not a pre-recorded track.
Perfect for a rules-compliant Alexa+ simulation.

**What needs work.**
- **`SpeechRecognition` quality varies by browser** (best in Chromium). Recognition
  of short command words is good but not perfect, which is exactly why our high-risk
  flow requires an explicit confirmation.
- **`speechSynthesis` failed silently on our setup.** On a Chrome/macOS machine with
  199 voices reported by `getVoices()`, calling `speechSynthesis.speak(...)` produced
  no audio at all — no error, no `onerror`, nothing. There is no reliable signal to
  tell "spoke" from "silently did nothing," so an app can't even detect the failure.
  We stopped fighting it and moved output to the host's own TTS (macOS `say`) behind
  a `/api/speak` endpoint, which was instantly reliable. A hard failure (or an
  accurate `onerror`) would have saved a long debugging session.
- **Self-hearing feedback loop.** With the mic open while the system speaks, TTS
  output was picked up by `SpeechRecognition` as a new "command," which re-triggered
  speech — an endless loop. We had to add explicit guards (ignore results while
  speaking, a short cooldown after speaking, and dedup of repeated phrases). A
  built-in "don't listen to my own output" mode would be a natural feature for any
  hands-free voice UI.
- **Overlapping playback needs its own guard.** Multiple browser tabs (or rapid
  requests) each triggered speech at once, so two voices talked over each other. We
  serialized server-side TTS (cancel the current utterance before starting the next)
  so only one voice is ever audible regardless of how many callers fire.

**Onboarding.** Trivial to start — a few dozen lines of vanilla JS. The hard part was
not the API surface but the silent-failure and feedback-loop behaviors above, which
only show up once you wire real hands-free interaction.

**Would we build with it again?** For a browser-based voice demo, yes — with the
caveat that reliable output meant falling back to host TTS. For production we'd move
to a dedicated STT/TTS (or Crew's built-in Piper/Transcribe voice).

---

## Summary

| Tool | Reuse? | One-line takeaway |
|---|---|---|
| Kiro Crew Gateway | ✅ | Great primitive; document the client auth shape. |
| Amazon Bedrock (Converse) | ✅ | Model-agnostic Converse made "rules + model" cheap and clean. |
| MCP Python SDK | ✅ | Streamable HTTP is easy; pick stateless mode behind a tunnel. |
| Alexa+ MCP bridge (AgentCore) | ✅ | Closest thing to real Alexa+ MCP; mind the long-lived session. |
| Web Speech API | ✅ (demo) | Honest, zero-dependency voice for the simulation. |
