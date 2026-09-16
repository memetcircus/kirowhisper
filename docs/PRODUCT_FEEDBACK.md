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

**Onboarding.** Fast, after resolving the 1.x-vs-2.x confusion. Introspecting the
installed package (`inspect.signature`) was the quickest way to get the current API.

**Would we build with it again?** Yes. Streamable HTTP support out of the box is
exactly what the Alexa+ track needs.

---

## Browser Web Speech API (STT + TTS)

**What we used it for.** The simulated Alexa+ voice surface: the user speaks (STT)
and the system replies aloud (TTS), all in the browser with zero dependencies.

**What worked well.** Zero install, low latency, and it kept the demo honest — it's
the user's *own* live voice in and a real-time voice out, not a pre-recorded track.
Perfect for a rules-compliant Alexa+ simulation.

**What needs work.** `SpeechRecognition` support and quality vary by browser (best in
Chromium). Recognition of short command words is good but not perfect, which is
exactly why our high-risk flow requires an explicit confirmation.

**Onboarding.** Trivial — a few dozen lines of vanilla JS.

**Would we build with it again?** For a browser-based voice demo, yes. For production
we'd move to a dedicated STT/TTS (or Crew's built-in Piper/Transcribe voice).

---

## Summary

| Tool | Reuse? | One-line takeaway |
|---|---|---|
| Kiro Crew Gateway | ✅ | Great primitive; document the client auth shape. |
| Amazon Bedrock (Converse) | ✅ | Model-agnostic Converse made "rules + model" cheap and clean. |
| MCP Python SDK | ✅ | Streamable HTTP is easy once you're past the 1.x→2.x rename. |
| Web Speech API | ✅ (demo) | Honest, zero-dependency voice for the simulation. |
