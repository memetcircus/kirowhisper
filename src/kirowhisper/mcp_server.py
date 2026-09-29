"""KiroWhisper MCP server — the outer face exposed over Streamable HTTP.

Satisfies the Alexa+ track's runtime-technology requirement (R12): a real MCP
server (spec 2025-11-25, Streamable HTTP) whose tools genuinely call the Crew
Gateway + Ambient Awareness engine at runtime — not merely named in a README.

Tools:
  - get_status            : overall status + ambient summary (passed/blocked/waiting)
  - get_pending_decisions : the decisions Ambient surfaced, voice-friendly
  - explain_top           : why the top decision is risky + what rejecting it does
  - approve_top           : approve the highest-risk pending decision (no id needed)
  - reject_top            : reject/skip the highest-risk pending decision (no id needed)
  - approve_all_safe      : approve all rule-certain low-risk waiting steps at once
  - approve               : approve a surfaced decision by request_id (low-level)
  - reject                : reject a surfaced decision by request_id (low-level)
  - trust_session         : auto-approve remaining low-risk steps this session
  - summarize             : voice-friendly summary of a task/diff

The voice flow is a two-call surface designed to be robust on assistants like
Alexa (no MCP elicitation back-channel across turns): get_pending_decisions to
hear the top decision, then approve_top / reject_top to act on it. approve/reject
by request_id remain for callers that already hold an id.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from mcp.server.mcpserver import MCPServer

from .ambient import AmbientEngine
from .audit import AuditLog
from .config import Config
from .gateway_client import ApprovalNotPendingError, GatewayClient, GatewayError
from .models import DecisionAction, RiskLevel
from .summarizer import Summarizer


@dataclass
class KiroWhisperServices:
    """Bundle of the core services the MCP tools operate on."""

    gateway: GatewayClient
    ambient: AmbientEngine
    summarizer: Summarizer
    audit: AuditLog
    config: Config


def build_server(services: KiroWhisperServices) -> MCPServer:
    """Wire the core services into an MCP server with voice-oriented tools."""
    mcp = MCPServer(
        name="kirowhisper",
        title="KiroWhisper",
        version="0.1.0",
        instructions=(
            "Voice oversight for autonomous Kiro Crew. Ask get_status for a spoken "
            "summary, get_pending_decisions for what needs you, then approve/reject."
        ),
    )
    svc = services
    # request_id -> deadline for an *armed* approval. approve_top never applies a
    # decision on its first call: it arms a confirmation and asks the user to say
    # yes/approve again. Only a second approve_top within the TTL actually approves.
    # This makes "does an ambiguous 'yes' apply a real decision?" a NO at the code
    # level, independent of how the voice model interprets the word — the safety is
    # deterministic, not prompt-dependent. Applies to EVERY decision, not just HIGH.
    pending_confirmations: dict[str, float] = {}
    confirmation_ttl_s = 30.0

    def prune_confirmations(live_ids: set[str]) -> None:
        """Forget confirmations that expired or no longer match a live decision."""
        now = time.monotonic()
        stale = [
            rid
            for rid, deadline in pending_confirmations.items()
            if rid not in live_ids or deadline <= now
        ]
        for rid in stale:
            pending_confirmations.pop(rid, None)

    @mcp.tool(
        description=(
            "Spoken status for 'get status', 'how is the crew doing', 'what did I miss': "
            "what Crew asked for since the user last checked, what was passed or "
            "blocked automatically, what the user decided, and how many decisions are "
            "still waiting. Read-only. Speak the result as given."
        ),
        structured_output=False,
    )
    async def get_status() -> str:
        # "While you were away": the window starts at the user's last status check
        # (persisted next to the audit log, so it survives restarts), or at process
        # start for a first-ever check.
        checkpoint = svc.audit.last_status_check()
        first_check = checkpoint is None
        digest = svc.audit.digest_since(svc.audit.started_at if first_check else checkpoint)
        try:
            gw_status = await svc.gateway.get_status()
        except GatewayError:
            gw_status = {}
        speech = svc.summarizer.status_digest(
            raised=digest.raised,
            auto_passed=digest.auto_passed,
            auto_blocked=digest.auto_blocked,
            you_approved=digest.you_approved,
            you_rejected=digest.you_rejected,
            waiting=len(svc.ambient.pending_decisions()),
            sessions=gw_status.get("sessions"),
            first_check=first_check,
        )
        svc.audit.mark_status_check()
        return speech

    @mcp.tool(
        description=(
            "THE tool to call for 'what needs my decision', 'what's waiting', 'anything "
            "for me', or to review/hear pending decisions. Speaks the most important "
            "decision first (highest risk) and tells the user to say 'approve it' or "
            "'reject it'. Read-only and always safe: it never approves or rejects "
            "anything. After speaking the decision, STOP and wait. Only if the user "
            "then EXPLICITLY says approve or reject should you call approve_top or "
            "reject_top; otherwise just answer and do nothing else."
        ),
        # structured_output=False: with the default auto-detect, a `-> str` return
        # still makes the SDK advertise an output schema ({"result": string}) AND wrap
        # the reply in structuredContent. The Alexa bridge then sends the model only
        # that JSON block and drops the spoken text, so the model treated our sentence
        # as data and skipped reading the decision aloud. It also broke on a warm
        # session that had cached an older output schema (-32602). Forcing NO structured
        # output makes this tool return a single plain-text block: words to speak, no
        # schema to drift, so the decision is actually read to an eyes-free user.
        structured_output=False,
    )
    async def get_pending_decisions() -> str:
        # (The stale-count risk that a structured `pending_count` once guarded against
        # is already handled at the source by AmbientEngine's ghost-entry cleanup.)
        pend = svc.ambient.pending_decisions()
        if not pend:
            return "Nothing needs you right now."
        # HIGH first, then the rest; voice-limit to 3 (NFR-3).
        pend.sort(key=lambda p: 0 if p.risk.level == RiskLevel.HIGH else 1)
        total = len(pend)
        top = pend[0]
        # fast=True: Alexa-turn latency budget; use pre-computed/deterministic text.
        summary = svc.summarizer.approval_summary(top.approval, top.risk, fast=True)
        head = f"{total} decisions are waiting. " if total > 1 else ""
        # Read the decision FIRST (what it is + why it may matter), THEN a neutral
        # question. Ends with "?" so the Alexa bridge keeps the mic open
        # (endsWithQuestion); neutral wording ("what would you like to do?") so a
        # stray "yes" isn't taken as approval — and approve_top confirms anyway.
        return (
            f"{head}The most important one: {summary}. "
            "What would you like to do — approve it, or reject it?"
        )

    @mcp.tool(
        description=(
            "Explain the waiting decision the user just heard: call this for "
            "'why is that risky', 'what does it do', 'what happens if I reject it', "
            "'tell me more', or any follow-up question about the top decision. "
            "Speaks WHY it carries its risk level and what rejecting it would do. "
            "Read-only and always safe: it never approves or rejects anything. After "
            "explaining, STOP and wait for the user to say approve or reject."
        ),
        # structured_output=False for the same reason as get_pending_decisions: the
        # Alexa bridge drops the spoken text when a tool advertises an output schema,
        # so this must be a single plain-text block the model reads aloud verbatim.
        structured_output=False,
    )
    async def explain_top() -> str:
        pend = svc.ambient.pending_decisions()
        if not pend:
            return "There's nothing waiting for you to explain right now."
        pend.sort(key=lambda p: 0 if p.risk.level == RiskLevel.HIGH else 1)
        top = pend[0]
        explanation = svc.summarizer.explain(top.approval, top.risk)
        # End on a neutral question so the Alexa mic stays open (endsWithQuestion)
        # and a stray "yes" isn't taken as approval — approve_top confirms anyway.
        return f"{explanation} Would you like to approve it, or reject it?"

    @mcp.tool(
        description=(
            "Approve the highest-risk waiting decision — no request id needed. "
            "EVERY approval takes TWO calls to this tool. First call: it returns a "
            "confirmation question and applies NOTHING. When the user then confirms "
            "(says yes, approve, confirm, go ahead, do it), you MUST CALL approve_top "
            "AGAIN — that second call is what actually approves. Speaking a "
            "confirmation without calling the tool again does nothing. Only skip the "
            "second call if the user clearly declines. Do not call this on a vague "
            "'yes' that was answering some other question — only when the user is "
            "approving the decision they just heard."
        )
    )
    async def approve_top() -> str:
        pend = svc.ambient.pending_decisions()
        live_ids = {item.approval.request_id for item in pend}
        prune_confirmations(live_ids)
        if not pend:
            return "There's nothing waiting for you right now."
        pend.sort(key=lambda p: 0 if p.risk.level == RiskLevel.HIGH else 1)
        top = pend[0]
        rid = top.approval.request_id

        # Every decision — not only HIGH-risk — needs an explicit second confirmation
        # before it is actually approved. The first approve_top only arms and asks;
        # nothing is applied. So even if the voice model mistakes a stray "yes" for an
        # approval and calls approve_top, no real change happens until the user says
        # yes/approve a second time. This is the deterministic guard behind Option A.
        deadline = pending_confirmations.get(rid)
        if deadline is None or deadline <= time.monotonic():
            pending_confirmations[rid] = time.monotonic() + confirmation_ttl_s
            summary = svc.summarizer.approval_summary(top.approval, top.risk, fast=True)
            extra = (
                " This is high-risk and may be irreversible."
                if top.risk.level == RiskLevel.HIGH
                else ""
            )
            # Keep this SHORT and end with a bare yes/no question. If the spoken
            # reply doesn't end in "?", the Alexa bridge (endsWithQuestion) closes the
            # session and the user's confirming "yes" goes to Alexa+, not this skill —
            # so the second approve_top never fires and nothing is applied. A short,
            # single question is the wording the model is least likely to rewrite into
            # a period-ending command.
            return f"{summary}.{extra} To confirm, are you sure you want to approve this?"
        pending_confirmations.pop(rid, None)

        taken = svc.ambient.take_pending(rid)
        if taken is None:
            return "That one was already handled."
        try:
            await svc.gateway.approve(taken.approval.slot, rid)
        except ApprovalNotPendingError:
            return "That approval expired or was already handled. Nothing was approved."
        except GatewayError as exc:
            svc.ambient.requeue(taken)
            return f"I couldn't apply the approval: {exc}. It's still pending."
        svc.audit.record(rid, taken.risk.level, DecisionAction.AUTO_APPROVE,
                         "user approved (voice, top)", by="user")
        remaining = len(svc.ambient.pending_decisions())
        tail = f" {remaining} more waiting." if remaining else ""
        return f"Approved. Continuing.{tail}"

    @mcp.tool(
        description=(
            "Reject (skip) the single most important waiting decision — no request id "
            "needed. Call this ONLY after the user has EXPLICITLY chosen to reject a "
            "decision they just heard (e.g. 'reject it', 'deny that', 'no, skip it'). "
            "A bare 'no', 'okay', or an ambiguous reply is NOT enough — do not act on "
            "it; ask a short confirming question instead. Rejecting is safe (the step "
            "just doesn't run), but it must still be the user's explicit choice."
        )
    )
    async def reject_top() -> str:
        pend = svc.ambient.pending_decisions()
        if not pend:
            return "There's nothing waiting for you right now."
        pend.sort(key=lambda p: 0 if p.risk.level == RiskLevel.HIGH else 1)
        top = pend[0]
        rid = top.approval.request_id
        pending_confirmations.pop(rid, None)
        taken = svc.ambient.take_pending(rid)
        if taken is None:
            return "That one was already handled."
        try:
            await svc.gateway.reject(taken.approval.slot, rid)
        except ApprovalNotPendingError:
            return "That approval expired or was already handled. Nothing was rejected."
        except GatewayError as exc:
            svc.ambient.requeue(taken)
            return f"I couldn't apply the rejection: {exc}. It's still pending."
        svc.audit.record(rid, taken.risk.level, DecisionAction.AUTO_BLOCK,
                         "user rejected (voice, top)", by="user")
        remaining = len(svc.ambient.pending_decisions())
        tail = f" {remaining} more waiting." if remaining else ""
        return f"I didn't do it. The task can continue past this step.{tail}"

    @mcp.tool(
        description=(
            "Approve every SAFE waiting decision at once — for 'approve all the safe "
            "ones', 'clear the safe ones', 'approve everything low-risk'. Approves "
            "only rule-certain low-risk steps (read/list/search); it never approves "
            "anything high-risk, uncertain, or catastrophic — those stay waiting for "
            "the user. Unlike trust_session it does NOT change how future steps are "
            "handled; it just clears the safe backlog once. Safe to call: the risky "
            "decisions are always left for the user to hear and decide."
        ),
        structured_output=False,
    )
    async def approve_all_safe() -> str:
        approved, remaining = await svc.ambient.approve_pending_safe()
        if approved == 0:
            if remaining:
                return (
                    "None of the waiting decisions are safe to auto-approve — they all "
                    f"need you. {remaining} still waiting. Say 'what needs my decision' "
                    "to hear them."
                )
            return "There are no safe decisions waiting to approve."
        noun = "step" if approved == 1 else "steps"
        if remaining:
            tail = (
                f" {remaining} riskier decision{'' if remaining == 1 else 's'} still "
                "need you."
            )
        else:
            tail = " Nothing riskier is waiting."
        return f"Approved {approved} safe {noun}.{tail}"

    @mcp.tool(
        description=(
            "Low-level: approve a specific decision by its exact request_id. Only use "
            "when you already have a request_id from a previous list. For normal voice "
            "approval, use approve_top (it needs no id)."
        )
    )
    async def approve(request_id: str, confirmed: bool = False) -> str:
        pending = svc.ambient.take_pending(request_id)
        if pending is None:
            return "I couldn't find that pending decision. It may have already been handled."
        # High-risk actions require an explicit second confirmation (R5.2).
        if pending.risk.level == RiskLevel.HIGH and not confirmed:
            svc.ambient.requeue(pending)  # keep it queued until confirmed
            summary = svc.summarizer.approval_summary(pending.approval, pending.risk)
            return f"{summary} This is high-risk. Say approve again with confirmed=true to proceed."
        try:
            await svc.gateway.approve(pending.approval.slot, request_id)
        except ApprovalNotPendingError:
            return "That approval expired or was already handled. Nothing was approved."
        except GatewayError as exc:
            svc.ambient.requeue(pending)
            return f"I couldn't apply the approval: {exc}. It's still pending."
        svc.audit.record(request_id, pending.risk.level, DecisionAction.AUTO_APPROVE,
                         "user approved", by="user")
        return "Approved. Continuing."

    @mcp.tool(
        description=(
            "Low-level: reject a specific decision by its exact request_id. Only use "
            "when you already have a request_id. For normal voice rejection, use "
            "reject_top instead (it needs no id)."
        )
    )
    async def reject(request_id: str) -> str:
        pending = svc.ambient.take_pending(request_id)
        if pending is None:
            return "I couldn't find that pending decision."
        pending_confirmations.pop(request_id, None)
        try:
            await svc.gateway.reject(pending.approval.slot, request_id)
        except ApprovalNotPendingError:
            return "That approval expired or was already handled. Nothing was rejected."
        except GatewayError as exc:
            svc.ambient.requeue(pending)
            return f"I couldn't apply the rejection: {exc}. It's still pending."
        svc.audit.record(request_id, pending.risk.level, DecisionAction.AUTO_BLOCK,
                         "user rejected", by="user")
        return "I didn't do it. The task can continue past this step."

    @mcp.tool(
        description="Trust this session: auto-approve remaining low-risk steps. "
        "High-risk and unknown steps will still be surfaced."
    )
    async def trust_session() -> str:
        svc.ambient.set_session_trust(True)
        # Also clear low-risk items ALREADY waiting, not just future ones — otherwise
        # "trust this session" leaves the current safe steps still asking, which feels
        # broken. Only rule-certain LOW clears; HIGH/UNKNOWN/model-guessed stay.
        cleared = await svc.ambient.apply_trust_to_pending()
        remaining = len(svc.ambient.pending_decisions())
        cleared_line = (
            f" I cleared {cleared} low-risk step(s) that were waiting." if cleared else ""
        )
        remaining_line = (
            f" {remaining} decision(s) still need you."
            if remaining
            else " Nothing else is waiting."
        )
        return (
            "Session trusted. I'll auto-approve low-risk steps and still ask you about "
            f"anything high-risk or uncertain.{cleared_line}{remaining_line}"
        )

    @mcp.tool(description="A short spoken summary of a task result or a diff.")
    async def summarize(task_id: str = "") -> str:
        if not task_id:
            return "Tell me which task to summarize."
        try:
            result = await svc.gateway.get_task_result(task_id)
        except GatewayError as exc:
            return f"I couldn't fetch that task: {exc}"
        done = result.get("done")
        turns = result.get("turns", 0)
        state = "done" if done else "still running"
        return f"Task {task_id[:8]} is {state} after {turns} turn(s)."

    return mcp
