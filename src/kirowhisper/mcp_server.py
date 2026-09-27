"""KiroWhisper MCP server — the outer face exposed over Streamable HTTP.

Satisfies the Alexa+ track's runtime-technology requirement (R12): a real MCP
server (spec 2025-11-25, Streamable HTTP) whose tools genuinely call the Crew
Gateway + Ambient Awareness engine at runtime — not merely named in a README.

Tools:
  - get_status            : overall status + ambient summary (passed/blocked/waiting)
  - get_pending_decisions : the decisions Ambient surfaced, voice-friendly
  - approve_top           : approve the highest-risk pending decision (no id needed)
  - reject_top            : reject/skip the highest-risk pending decision (no id needed)
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


@dataclass
class PendingDecisionsResult:
    """Structured return for get_pending_decisions.

    ``pending_count`` is a real numeric field, not folded into ``speech``.
    Long-lived Alexa/AgentCore sessions keep up to 40 prior turns of chat
    history in the model's context; a bare-string tool result invites the
    model to paraphrase from that history instead of this turn's fresh
    number (observed live: a stale "six decisions waiting" persisting after
    the backend and this tool both already agreed on one). MCP marks
    structured content as authoritative over prose (see the bridge's
    tool-result reading rules), so a dedicated int field is the fix that
    actually reaches the model, not just a comment.
    """

    speech: str
    pending_count: int


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
    high_risk_confirmations: dict[str, float] = {}
    confirmation_ttl_s = 30.0

    def prune_confirmations(live_ids: set[str]) -> None:
        """Forget confirmations that expired or no longer match a live decision."""
        now = time.monotonic()
        stale = [
            rid
            for rid, deadline in high_risk_confirmations.items()
            if rid not in live_ids or deadline <= now
        ]
        for rid in stale:
            high_risk_confirmations.pop(rid, None)

    @mcp.tool(description="Spoken overall status: what Crew is doing and what Ambient handled.")
    async def get_status() -> str:
        snap = svc.ambient.snapshot()
        try:
            gw_status = await svc.gateway.get_status()
        except GatewayError:
            gw_status = {}
        ambient_line = svc.summarizer.ambient_summary(
            auto_passed=snap.get(DecisionAction.AUTO_APPROVE.value, 0),
            blocked=snap.get(DecisionAction.AUTO_BLOCK.value, 0),
            surfaced=snap.get("pending", 0),
        )
        sessions = gw_status.get("sessions")
        tail = f" Crew has {sessions} active session(s)." if sessions is not None else ""
        return ambient_line + tail

    @mcp.tool(
        description=(
            "THE tool to call for 'what needs my decision', 'what's waiting', 'anything "
            "for me', or to review/hear pending decisions. Speaks the most important "
            "decision first (highest risk) and tells the user to say 'approve it' or "
            "'reject it'. One quick call, no follow-up question — always safe on a "
            "voice assistant. After the user answers, call approve_top or reject_top."
        )
    )
    async def get_pending_decisions() -> PendingDecisionsResult:
        pend = svc.ambient.pending_decisions()
        if not pend:
            return PendingDecisionsResult(speech="Nothing needs you right now.", pending_count=0)
        # HIGH first, then the rest; voice-limit to 3 (NFR-3).
        pend.sort(key=lambda p: 0 if p.risk.level == RiskLevel.HIGH else 1)
        total = len(pend)
        top = pend[0]
        # fast=True: Alexa-turn latency budget; use pre-computed/deterministic text.
        summary = svc.summarizer.approval_summary(top.approval, top.risk, fast=True)
        head = f"{total} decisions are waiting. " if total > 1 else ""
        # End with a literal question mark: the Alexa bridge keeps the microphone open
        # only when the spoken reply ends in '?' (endsWithQuestion). Without it the
        # session closes and the user's next words (e.g. "reject it") go to Alexa
        # itself instead of back to this skill.
        prompt = " Should I approve it, or reject it?"
        speech = f"{head}First: {summary}{prompt}"
        # pending_count is real structured content (see PendingDecisionsResult):
        # this turn's true, current count, so the model has no reason to fall
        # back on a number it said in an earlier turn of a long-lived session.
        return PendingDecisionsResult(speech=speech, pending_count=total)

    @mcp.tool(
        description=(
            "Approve the single most important decision currently waiting (highest "
            "risk first) — no request id needed. For HIGH-risk decisions, the first "
            "call asks for an explicit second confirmation without acting; call "
            "approve_top again only after the user confirms. LOW-risk decisions need "
            "one call. Use for approve, yes, allow, confirm, or 'do it'."
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

        if top.risk.level == RiskLevel.HIGH:
            deadline = high_risk_confirmations.get(rid)
            if deadline is None or deadline <= time.monotonic():
                high_risk_confirmations[rid] = time.monotonic() + confirmation_ttl_s
                summary = svc.summarizer.approval_summary(
                    top.approval, top.risk, fast=True
                )
                return (
                    f"{summary} This is high-risk and may be irreversible. "
                    "Are you sure I should approve it?"
                )
            high_risk_confirmations.pop(rid, None)

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
            "Reject (skip) the single most important decision currently waiting — no "
            "request id needed. Use when the user says reject, no, deny, skip, or "
            "'don't' after hearing a decision. One quick call, reliable on Alexa."
        )
    )
    async def reject_top() -> str:
        pend = svc.ambient.pending_decisions()
        if not pend:
            return "There's nothing waiting for you right now."
        pend.sort(key=lambda p: 0 if p.risk.level == RiskLevel.HIGH else 1)
        top = pend[0]
        rid = top.approval.request_id
        high_risk_confirmations.pop(rid, None)
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
        high_risk_confirmations.pop(request_id, None)
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
        return ("Session trusted. I'll auto-approve low-risk steps and still ask you "
                "about anything high-risk or uncertain.")

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
