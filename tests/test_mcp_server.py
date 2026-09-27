"""Tests for the MCP server tools, using fake services (no network/model).

Verifies tool registration and the behavior of approve/reject/status, including
the high-risk double-confirm flow.
"""

from __future__ import annotations

from pathlib import Path

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
    # Accessibility requirement: an eyes-free user must HEAR what the decision is, so
    # the spoken text must include the decision summary itself, not just a question.
    assert "spoken" in out.lower()          # the risk assessment's spoken_summary
    # Offers both choices and ends with a question (keeps the Alexa mic open).
    assert "approve" in out.lower() and "reject" in out.lower()
    assert out.rstrip().endswith("?")
    # Plain string now (no JSON wrapper), so the bridge speaks it as words.
    assert not out.lstrip().startswith("{")


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


# ---- approve_top / reject_top (the Alexa-reliable, no-elicitation path) ------


async def test_approve_top_confirms_high_risk_then_approves_it_first(tmp_path: Path):
    svc, gw, ambient = _services(tmp_path)
    _surface(ambient, "low1", RiskLevel.LOW, slot="s1")
    _surface(ambient, "high1", RiskLevel.HIGH, slot="s2")
    server = build_server(svc)

    first = await _call(server, "approve_top")
    assert "high-risk" in first.lower()
    assert first.endswith("?")
    assert gw.approved == []
    assert any(p.approval.request_id == "high1" for p in ambient.pending_decisions())

    second = await _call(server, "approve_top")
    assert "approved" in second.lower()
    assert gw.approved == ["high1"]              # HIGH went first
    assert ambient.take_pending("high1") is None  # removed from queue
    assert ambient.take_pending("low1") is not None  # low still waiting


async def test_approve_top_confirms_low_risk_too(tmp_path: Path):
    # Option A: even a LOW-risk decision needs a second, explicit confirmation, so an
    # ambiguous "yes" that the voice model mis-read as approve can never apply a real
    # decision on the first call.
    svc, gw, ambient = _services(tmp_path)
    _surface(ambient, "low1", RiskLevel.LOW)
    server = build_server(svc)

    first = await _call(server, "approve_top")
    assert first.rstrip().endswith("?")          # asks to confirm, does not apply
    assert gw.approved == []
    assert any(p.approval.request_id == "low1" for p in ambient.pending_decisions())

    second = await _call(server, "approve_top")
    assert "approved" in second.lower()
    assert gw.approved == ["low1"]               # applied only on the second call


async def test_reject_top_rejects_highest_risk_first(tmp_path: Path):
    svc, gw, ambient = _services(tmp_path)
    _surface(ambient, "high2", RiskLevel.HIGH)
    server = build_server(svc)
    out = await _call(server, "reject_top")
    assert "didn't do it" in out.lower()
    assert gw.rejected == ["high2"]


async def test_approve_top_nothing_pending(tmp_path: Path):
    svc, gw, _ = _services(tmp_path)
    server = build_server(svc)
    out = await _call(server, "approve_top")
    assert "nothing waiting" in out.lower()
    assert gw.approved == []
