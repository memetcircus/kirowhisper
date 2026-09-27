"""Tests for the voice-simulation JSON bridge, using Starlette's TestClient."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from kirowhisper.ambient import AmbientEngine
from kirowhisper.audit import AuditLog
from kirowhisper.config import AmbientConfig, BedrockConfig, Config
from kirowhisper.mcp_server import KiroWhisperServices
from kirowhisper.models import Approval, PendingDecision, RiskAssessment, RiskLevel
from kirowhisper.risk import RiskClassifier
from kirowhisper.summarizer import Summarizer
from kirowhisper.voice_sim.bridge import VoiceBridge


class FakeGateway:
    def __init__(self):
        self.approved = []
        self.rejected = []

    async def get_status(self):
        return {"sessions": 1}

    async def approve(self, slot, rid):
        self.approved.append(rid)

    async def reject(self, slot, rid):
        self.rejected.append(rid)


def _bridge(tmp_path: Path):
    gw = FakeGateway()
    audit = AuditLog(path=tmp_path / "a.jsonl")
    ambient = AmbientEngine(gw, RiskClassifier(), audit, AmbientConfig())
    svc = KiroWhisperServices(
        gateway=gw, ambient=ambient,
        summarizer=Summarizer(BedrockConfig()), audit=audit, config=Config(),
    )
    return VoiceBridge(svc), gw, ambient


def _surface(ambient, rid, level):
    ap = Approval(request_id=rid, slot="s", tool_title="Delete auth.js", diff="-x")
    ambient.requeue(PendingDecision(approval=ap, risk=RiskAssessment(level, "r", "spoken text")))


def test_index_serves_ui(tmp_path: Path):
    bridge, _, _ = _bridge(tmp_path)
    client = TestClient(bridge.app())
    r = client.get("/")
    assert r.status_code == 200
    assert "KiroWhisper" in r.text
    assert "Simulated Alexa+" in r.text


def test_status_endpoint(tmp_path: Path):
    bridge, _, _ = _bridge(tmp_path)
    client = TestClient(bridge.app())
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert "spoken" in data
    assert data["sessions"] == 1


def test_pending_lists_high_first(tmp_path: Path):
    bridge, _, ambient = _bridge(tmp_path)
    _surface(ambient, "low1", RiskLevel.LOW)
    _surface(ambient, "high1", RiskLevel.HIGH)
    client = TestClient(bridge.app())
    r = client.get("/api/pending")
    items = r.json()["pending"]
    assert items[0]["request_id"] == "high1"   # high risk sorted first
    assert items[0]["risk"] == "high"


def test_approve_low_risk(tmp_path: Path):
    bridge, gw, ambient = _bridge(tmp_path)
    _surface(ambient, "r1", RiskLevel.LOW)
    client = TestClient(bridge.app())
    r = client.post("/api/approve", json={"request_id": "r1"})
    assert r.json()["ok"] is True
    assert gw.approved == ["r1"]


def test_approve_high_needs_confirmation(tmp_path: Path):
    bridge, gw, ambient = _bridge(tmp_path)
    _surface(ambient, "r2", RiskLevel.HIGH)
    client = TestClient(bridge.app())
    r = client.post("/api/approve", json={"request_id": "r2"})
    body = r.json()
    assert body["ok"] is False
    assert body["needs_confirmation"] is True
    assert gw.approved == []
    # confirm
    r2 = client.post("/api/approve", json={"request_id": "r2", "confirmed": True})
    assert r2.json()["ok"] is True
    assert gw.approved == ["r2"]


def test_reject(tmp_path: Path):
    bridge, gw, ambient = _bridge(tmp_path)
    _surface(ambient, "r3", RiskLevel.HIGH)
    client = TestClient(bridge.app())
    r = client.post("/api/reject", json={"request_id": "r3"})
    assert r.json()["ok"] is True
    assert gw.rejected == ["r3"]


def test_trust(tmp_path: Path):
    bridge, _, ambient = _bridge(tmp_path)
    client = TestClient(bridge.app())
    r = client.post("/api/trust", json={})
    assert r.json()["ok"] is True
    assert ambient._session_trust is True  # noqa: SLF001 - verifying wiring


def test_approve_unknown_id(tmp_path: Path):
    bridge, _, _ = _bridge(tmp_path)
    client = TestClient(bridge.app())
    r = client.post("/api/approve", json={"request_id": "nope"})
    assert r.json()["ok"] is False
