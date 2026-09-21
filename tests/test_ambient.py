"""Unit tests for the Ambient Awareness engine and decision policy.

Uses a fake Gateway + fake classifier so the three-bucket routing, idempotency,
and fail-safe behavior are tested without any network or model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kirowhisper.ambient import AmbientEngine
from kirowhisper.audit import AuditLog
from kirowhisper.config import AmbientConfig
from kirowhisper.gateway_client import GatewayError
from kirowhisper.models import Approval, DecisionAction, RiskAssessment, RiskLevel
from kirowhisper.policy import decide

# ── policy (pure) ──

def test_policy_high_and_unknown_surface():
    assert decide(RiskAssessment(RiskLevel.HIGH, "x"))[0] == DecisionAction.SURFACE
    assert decide(RiskAssessment(RiskLevel.UNKNOWN, "x"))[0] == DecisionAction.SURFACE


def test_policy_low_needs_trust():
    assert decide(RiskAssessment(RiskLevel.LOW, "x"))[0] == DecisionAction.SURFACE
    trusted = decide(RiskAssessment(RiskLevel.LOW, "x"), session_trust=True)[0]
    assert trusted == DecisionAction.AUTO_APPROVE


def test_policy_explicit_deny_blocks():
    action, _ = decide(RiskAssessment(RiskLevel.LOW, "x"), session_trust=True, explicit_deny=True)
    assert action == DecisionAction.AUTO_BLOCK


def test_policy_trust_never_overrides_safety():
    result = decide(RiskAssessment(RiskLevel.HIGH, "x"), session_trust=True)[0]
    assert result == DecisionAction.SURFACE


# ── fakes ──

class FakeGateway:
    def __init__(self, approvals, *, fail_resolve=False):
        self._approvals = approvals
        self.approved: list[str] = []
        self.rejected: list[str] = []
        self._fail_resolve = fail_resolve

    async def list_pending_approvals(self):
        return list(self._approvals)

    async def approve(self, slot, request_id):
        if self._fail_resolve:
            raise GatewayError("resolve down")
        self.approved.append(request_id)

    async def reject(self, slot, request_id):
        if self._fail_resolve:
            raise GatewayError("resolve down")
        self.rejected.append(request_id)


class FailingGateway:
    async def list_pending_approvals(self):
        raise GatewayError("gateway down")


class FixedClassifier:
    """Returns a fixed risk level regardless of the approval."""

    def __init__(self, level: RiskLevel):
        self._level = level

    def classify(self, _approval):
        return RiskAssessment(self._level, f"{self._level} fixed")


def _ap(rid: str, slot: str = "s") -> Approval:
    return Approval(request_id=rid, slot=slot, tool_title="op")


def _engine(gateway, classifier, tmp_path, **kw) -> AmbientEngine:
    audit = AuditLog(path=tmp_path / "audit.jsonl")
    cfg = AmbientConfig()
    return AmbientEngine(gateway, classifier, audit, cfg, **kw)


# ── three-bucket routing ──

async def test_high_risk_is_surfaced_not_approved(tmp_path: Path):
    gw = FakeGateway([_ap("r1")])
    eng = _engine(gw, FixedClassifier(RiskLevel.HIGH), tmp_path)
    decisions = await eng.poll_once()
    assert decisions[0].action == DecisionAction.SURFACE
    assert gw.approved == []                      # never auto-approved
    assert len(eng.pending_decisions()) == 1      # queued for the user


async def test_low_with_trust_is_auto_approved(tmp_path: Path):
    gw = FakeGateway([_ap("r2")])
    eng = _engine(gw, FixedClassifier(RiskLevel.LOW), tmp_path, session_trust=True)
    await eng.poll_once()
    assert gw.approved == ["r2"]
    assert eng.pending_decisions() == []


async def test_low_without_trust_is_surfaced(tmp_path: Path):
    gw = FakeGateway([_ap("r3")])
    eng = _engine(gw, FixedClassifier(RiskLevel.LOW), tmp_path, session_trust=False)
    await eng.poll_once()
    assert gw.approved == []
    assert len(eng.pending_decisions()) == 1


async def test_explicit_deny_is_auto_blocked(tmp_path: Path):
    gw = FakeGateway([_ap("r4")])
    eng = _engine(gw, FixedClassifier(RiskLevel.LOW), tmp_path,
                  session_trust=True, deny_check=lambda a: True)
    await eng.poll_once()
    assert gw.rejected == ["r4"]
    assert gw.approved == []


async def test_unknown_is_surfaced(tmp_path: Path):
    gw = FakeGateway([_ap("r5")])
    eng = _engine(gw, FixedClassifier(RiskLevel.UNKNOWN), tmp_path, session_trust=True)
    await eng.poll_once()
    assert gw.approved == []
    assert len(eng.pending_decisions()) == 1


# ── idempotency ──

async def test_each_approval_processed_once(tmp_path: Path):
    gw = FakeGateway([_ap("r6")])
    eng = _engine(gw, FixedClassifier(RiskLevel.LOW), tmp_path, session_trust=True)
    await eng.poll_once()
    await eng.poll_once()  # same approval still pending on the gateway
    assert gw.approved == ["r6"]  # approved only once


# ── proactive callback ──

async def test_surface_fires_callback(tmp_path: Path):
    seen = []

    async def on_surface(pending):
        seen.append(pending.approval.request_id)

    gw = FakeGateway([_ap("r7")])
    eng = _engine(gw, FixedClassifier(RiskLevel.HIGH), tmp_path, on_surface=on_surface)
    await eng.poll_once()
    assert seen == ["r7"]


# ── fail-safe ──

async def test_gateway_down_raises_and_auto_passes_nothing(tmp_path: Path):
    eng = _engine(FailingGateway(), FixedClassifier(RiskLevel.LOW), tmp_path, session_trust=True)
    with pytest.raises(GatewayError):
        await eng.poll_once()
    assert eng.pending_decisions() == []  # nothing fabricated


async def test_resolve_failure_drops_back_to_pending(tmp_path: Path):
    # Auto-approve intended, but the Gateway resolve fails -> must resurface, not swallow.
    gw = FakeGateway([_ap("r8")], fail_resolve=True)
    eng = _engine(gw, FixedClassifier(RiskLevel.LOW), tmp_path, session_trust=True)
    await eng.poll_once()
    assert len(eng.pending_decisions()) == 1


# ── stale/ghost pending cleanup ──


async def test_deleted_approval_is_dropped_from_pending(tmp_path: Path):
    """A surfaced decision whose Crew slot/approval disappears (deleted, expired,
    resolved elsewhere) must not linger in _pending forever. Reproduces a live bug:
    get_pending_decisions reported a growing count (up to '6 decisions waiting')
    for ghost entries whose underlying approval no longer existed on the Gateway.
    """
    approvals = [_ap("ghost1")]
    gw = FakeGateway(approvals)
    eng = _engine(gw, FixedClassifier(RiskLevel.HIGH), tmp_path)
    await eng.poll_once()
    assert len(eng.pending_decisions()) == 1

    # The underlying approval vanishes from the Gateway (slot deleted, expired, ...).
    approvals.clear()
    await eng.poll_once()
    assert eng.pending_decisions() == []  # no longer reported


async def test_reappearing_approval_after_cleanup_is_resurfaced(tmp_path: Path):
    """If a stale id is cleaned up and the same id later reappears (edge case), it
    must be treated as new again rather than silently ignored via _seen.
    """
    approvals = [_ap("flappy")]
    gw = FakeGateway(approvals)
    eng = _engine(gw, FixedClassifier(RiskLevel.HIGH), tmp_path)
    await eng.poll_once()
    assert len(eng.pending_decisions()) == 1

    approvals.clear()
    await eng.poll_once()
    assert eng.pending_decisions() == []

    approvals.append(_ap("flappy"))
    await eng.poll_once()
    assert len(eng.pending_decisions()) == 1  # surfaced again, not skipped as "seen"


async def test_unrelated_pending_survives_cleanup(tmp_path: Path):
    """Cleanup must only drop ids that vanished, not everything."""
    approvals = [_ap("keep"), _ap("gone")]
    gw = FakeGateway(approvals)
    eng = _engine(gw, FixedClassifier(RiskLevel.HIGH), tmp_path)
    await eng.poll_once()
    assert len(eng.pending_decisions()) == 2

    approvals[:] = [a for a in approvals if a.request_id != "gone"]
    await eng.poll_once()
    remaining = {p.approval.request_id for p in eng.pending_decisions()}
    assert remaining == {"keep"}


# ── snapshot ──

async def test_snapshot_counts(tmp_path: Path):
    gw = FakeGateway([_ap("a"), _ap("b"), _ap("c")])
    eng = _engine(gw, FixedClassifier(RiskLevel.HIGH), tmp_path)
    await eng.poll_once()
    snap = eng.snapshot()
    assert snap["surface"] == 3
    assert snap["pending"] == 3
