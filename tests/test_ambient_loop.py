"""Tests for the ambient background loop timing and lifecycle."""

from __future__ import annotations

import asyncio
from pathlib import Path

from kirowhisper.ambient import AmbientEngine
from kirowhisper.audit import AuditLog
from kirowhisper.config import AmbientConfig
from kirowhisper.gateway_client import GatewayError
from kirowhisper.models import RiskAssessment, RiskLevel
from kirowhisper.risk import RiskClassifier


class CountingGateway:
    def __init__(self):
        self.polls = 0

    async def list_pending_approvals(self):
        self.polls += 1
        return []


class FixedClassifier:
    def classify(self, _a):
        return RiskAssessment(RiskLevel.LOW, "x")


def _engine(gw, tmp_path, poll_interval):
    audit = AuditLog(path=tmp_path / "a.jsonl")
    cfg = AmbientConfig(poll_interval_s=poll_interval)
    return AmbientEngine(gw, RiskClassifier(), audit, cfg)


async def test_loop_respects_poll_interval(tmp_path: Path):
    # With a small interval, over ~0.25s we expect a bounded number of polls,
    # not a tight busy-loop hammering the gateway.
    gw = CountingGateway()
    eng = _engine(gw, tmp_path, poll_interval=0.1)
    eng.start()
    await asyncio.sleep(0.25)
    await eng.stop()
    # ~3 polls expected (t=0, 0.1, 0.2); allow slack but reject a busy loop.
    assert 1 <= gw.polls <= 6


async def test_loop_stop_is_clean(tmp_path: Path):
    gw = CountingGateway()
    eng = _engine(gw, tmp_path, poll_interval=0.05)
    eng.start()
    await asyncio.sleep(0.02)
    await eng.stop()  # must not raise
    polls_after_stop = gw.polls
    await asyncio.sleep(0.1)
    # No further polling after stop.
    assert gw.polls == polls_after_stop


class FlakyGateway:
    def __init__(self):
        self.calls = 0

    async def list_pending_approvals(self):
        self.calls += 1
        raise GatewayError("down")


async def test_loop_survives_gateway_errors(tmp_path: Path):
    # Gateway keeps failing; the loop must keep running (backoff) and not crash.
    gw = FlakyGateway()
    eng = _engine(gw, tmp_path, poll_interval=0.05)
    eng.start()
    await asyncio.sleep(0.2)
    await eng.stop()
    assert gw.calls >= 1          # it tried
    assert eng.pending_decisions() == []  # nothing fabricated on failure
