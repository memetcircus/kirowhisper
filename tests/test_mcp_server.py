"""Tests for the MCP server tools, using fake services (no network/model).

Verifies tool registration and the behavior of approve/reject/status, including
the high-risk double-confirm flow.
"""

from __future__ import annotations

from pathlib import Path

import mcp.types as mcp_types
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

from kirowhisper.ambient import AmbientEngine
from kirowhisper.audit import AuditLog
from kirowhisper.config import AmbientConfig, BedrockConfig, Config
from kirowhisper.mcp_server import KiroWhisperServices, build_server
from kirowhisper.models import Approval, PendingDecision, RiskAssessment, RiskLevel
from kirowhisper.risk import RiskClassifier
from kirowhisper.summarizer import Summarizer


class FakeGateway:
    def __init__(self):
        self.approved = []
        self.rejected = []

    async def get_status(self):
        return {"sessions": 2}

    async def approve(self, slot, request_id):
        self.approved.append(request_id)

    async def reject(self, slot, request_id):
        self.rejected.append(request_id)

    async def get_task_result(self, task_id):
        return {"done": True, "turns": 3}


def _services(tmp_path: Path):
    gw = FakeGateway()
    audit = AuditLog(path=tmp_path / "audit.jsonl")
    ambient = AmbientEngine(gw, RiskClassifier(), audit, AmbientConfig())
    summarizer = Summarizer(BedrockConfig())
    svc = KiroWhisperServices(
        gateway=gw, ambient=ambient, summarizer=summarizer, audit=audit, config=Config()
    )
    return svc, gw, ambient


def _surface(ambient, rid, level, slot="s"):
    ap = Approval(request_id=rid, slot=slot, tool_title="Delete auth.js", diff="-x")
    ambient.requeue(PendingDecision(approval=ap, risk=RiskAssessment(level, "reason", "spoken")))


async def _call(server, name, **kwargs):
    """Invoke a registered MCP tool by name and return its text result."""
    result = await server.call_tool(name, kwargs)
    # MCP returns structured content; normalize to text.
    if isinstance(result, tuple):
        result = result[0]
    if hasattr(result, "content"):
        parts = [c.text for c in result.content if hasattr(c, "text")]
        return " ".join(parts)
    return str(result)


def test_server_builds_and_registers_tools(tmp_path: Path):
    svc, _, _ = _services(tmp_path)
    server = build_server(svc)
    assert server.name == "kirowhisper"


async def test_get_pending_decisions_empty(tmp_path: Path):
    svc, _, _ = _services(tmp_path)
    server = build_server(svc)
    out = await _call(server, "get_pending_decisions")
    assert "nothing needs you" in out.lower()


async def test_get_pending_decisions_lists_surfaced(tmp_path: Path):
    svc, _, ambient = _services(tmp_path)
    _surface(ambient, "r1", RiskLevel.HIGH)
    server = build_server(svc)
    out = await _call(server, "get_pending_decisions")
    assert "1." in out


async def test_approve_high_risk_requires_confirmation(tmp_path: Path):
    svc, gw, ambient = _services(tmp_path)
    _surface(ambient, "r2", RiskLevel.HIGH)
    server = build_server(svc)
    out = await _call(server, "approve", request_id="r2")
    assert "high-risk" in out.lower()
    assert gw.approved == []                    # not approved yet
    assert ambient.take_pending("r2") is not None  # still queued


async def test_approve_high_risk_confirmed(tmp_path: Path):
    svc, gw, ambient = _services(tmp_path)
    _surface(ambient, "r3", RiskLevel.HIGH)
    server = build_server(svc)
    out = await _call(server, "approve", request_id="r3", confirmed=True)
    assert "approved" in out.lower()
    assert gw.approved == ["r3"]


async def test_approve_low_risk_no_confirmation_needed(tmp_path: Path):
    svc, gw, ambient = _services(tmp_path)
    _surface(ambient, "r4", RiskLevel.LOW)
    server = build_server(svc)
    out = await _call(server, "approve", request_id="r4")
    assert "approved" in out.lower()
    assert gw.approved == ["r4"]


async def test_reject_reassures(tmp_path: Path):
    svc, gw, ambient = _services(tmp_path)
    _surface(ambient, "r5", RiskLevel.HIGH)
    server = build_server(svc)
    out = await _call(server, "reject", request_id="r5")
    assert "didn't do it" in out.lower()
    assert gw.rejected == ["r5"]


async def test_approve_unknown_request_id(tmp_path: Path):
    svc, _, _ = _services(tmp_path)
    server = build_server(svc)
    out = await _call(server, "approve", request_id="nope")
    assert "couldn't find" in out.lower()


async def test_trust_session_enables_trust(tmp_path: Path):
    svc, _, ambient = _services(tmp_path)
    server = build_server(svc)
    out = await _call(server, "trust_session")
    assert "trusted" in out.lower()


async def test_get_status_includes_ambient_and_sessions(tmp_path: Path):
    svc, _, _ = _services(tmp_path)
    server = build_server(svc)
    out = await _call(server, "get_status")
    assert "session" in out.lower()


# ---- Elicitation-driven triage flow (the Alexa+ bridge path) ----------------
#
# triage_next_decision asks the user a question mid-call (elicitation) and acts on
# the answer. We test it end to end over an in-memory client/server connection,
# with the client auto-answering the elicitation the way the bridge would.

async def _run_triage_with_answers(server, answers):
    """Call triage_next_decision over a real MCP connection, auto-answering each
    elicitation with the next value from `answers` (a list of dicts, one per
    elicit call). Returns the tool's final text output.
    """
    import anyio

    replies = list(answers)

    async def elicitation_callback(context, params):
        content = replies.pop(0) if replies else None
        if content is None:
            return mcp_types.ElicitResult(action="decline")
        return mcp_types.ElicitResult(action="accept", content=content)

    async with create_client_server_memory_streams() as ((cr, cw), (sr, sw)):
        async with anyio.create_task_group() as tg:

            async def run_server():
                low = server._lowlevel_server  # low-level server behind MCPServer
                await low.run(sr, sw, low.create_initialization_options())

            tg.start_soon(run_server)
            async with ClientSession(
                cr, cw, elicitation_callback=elicitation_callback
            ) as session:
                await session.initialize()
                result = await session.call_tool("triage_next_decision", {})
                tg.cancel_scope.cancel()

    parts = [c.text for c in result.content if hasattr(c, "text")]
    return " ".join(parts)


async def test_triage_approve_low_risk(tmp_path: Path):
    svc, gw, ambient = _services(tmp_path)
    _surface(ambient, "t1", RiskLevel.LOW)
    server = build_server(svc)
    out = await _run_triage_with_answers(server, [{"decision": "approve"}])
    assert "approved" in out.lower()
    assert gw.approved == ["t1"]


async def test_triage_reject(tmp_path: Path):
    svc, gw, ambient = _services(tmp_path)
    _surface(ambient, "t2", RiskLevel.LOW)
    server = build_server(svc)
    out = await _run_triage_with_answers(server, [{"decision": "reject"}])
    assert "didn't do it" in out.lower()
    assert gw.rejected == ["t2"]


async def test_triage_high_risk_needs_second_confirmation(tmp_path: Path):
    svc, gw, ambient = _services(tmp_path)
    _surface(ambient, "t3", RiskLevel.HIGH)
    server = build_server(svc)
    # First answer approves; second (yes) confirms the high-risk action.
    out = await _run_triage_with_answers(
        server, [{"decision": "approve"}, {"yes": True}]
    )
    assert "approved" in out.lower()
    assert gw.approved == ["t3"]


async def test_triage_high_risk_declined_confirmation_does_not_approve(tmp_path: Path):
    svc, gw, ambient = _services(tmp_path)
    _surface(ambient, "t4", RiskLevel.HIGH)
    server = build_server(svc)
    await _run_triage_with_answers(server, [{"decision": "approve"}, {"yes": False}])
    assert gw.approved == []               # not approved
    assert ambient.take_pending("t4") is not None  # still queued


async def test_triage_nothing_pending(tmp_path: Path):
    svc, _, _ = _services(tmp_path)
    server = build_server(svc)
    out = await _run_triage_with_answers(server, [])
    assert "nothing needs you" in out.lower()
