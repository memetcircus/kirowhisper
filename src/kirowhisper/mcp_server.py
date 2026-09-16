"""KiroWhisper MCP server — the outer face exposed over Streamable HTTP.

Satisfies the Alexa+ track's runtime-technology requirement (R12): a real MCP
server (spec 2025-11-25, Streamable HTTP) whose tools genuinely call the Crew
Gateway + Ambient Awareness engine at runtime — not merely named in a README.

Tools:
  - get_status            : overall status + ambient summary (passed/blocked/waiting)
  - get_pending_decisions : the decisions Ambient surfaced, voice-friendly
  - approve               : approve a surfaced decision (double-confirm hint if HIGH)
  - reject                : reject a surfaced decision (skip); pause/cancel handled by caller
  - trust_session         : auto-approve remaining low-risk steps this session
  - summarize             : voice-friendly summary of a task/diff
"""

from __future__ import annotations

from dataclasses import dataclass

from mcp.server.mcpserver import MCPServer

from .ambient import AmbientEngine
from .audit import AuditLog
from .config import Config
from .gateway_client import GatewayClient, GatewayError
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

    @mcp.tool(description="What needs your decision right now, spoken and prioritized.")
    async def get_pending_decisions() -> str:
        pend = svc.ambient.pending_decisions()
        if not pend:
            return "Nothing needs you right now."
        # HIGH first, then the rest; voice-limit to 3 (NFR-3).
        pend.sort(key=lambda p: 0 if p.risk.level == RiskLevel.HIGH else 1)
        lines = []
        for i, p in enumerate(pend[:3], 1):
            lines.append(f"{i}. " + svc.summarizer.approval_summary(p.approval, p.risk))
        more = "" if len(pend) <= 3 else f" And {len(pend) - 3} more."
        return " ".join(lines) + more

    @mcp.tool(
        description="Approve a surfaced decision by its request_id. "
        "Returns a confirmation prompt first if the action is high-risk."
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
        except GatewayError as exc:
            svc.ambient.requeue(pending)
            return f"I couldn't apply the approval: {exc}. It's still pending."
        svc.audit.record(request_id, pending.risk.level, DecisionAction.AUTO_APPROVE,
                         "user approved", by="user")
        return "Approved. Continuing."

    @mcp.tool(description="Reject a surfaced decision by its request_id (skip this step).")
    async def reject(request_id: str) -> str:
        pending = svc.ambient.take_pending(request_id)
        if pending is None:
            return "I couldn't find that pending decision."
        try:
            await svc.gateway.reject(pending.approval.slot, request_id)
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
