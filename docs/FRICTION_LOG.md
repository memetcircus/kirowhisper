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

---

## Severity tally
- High: F1, F2
- Medium: F3, F4, F5, F7
- Low: F6

Most frictions were about **discovery** (how to talk to the Gateway, which action
string, where the pending approval lives) rather than capability gaps — the
capabilities were all there. Better client docs would remove the majority of these.
