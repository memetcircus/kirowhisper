"""Integration smoke test against a REAL local Kiro Crew Gateway.

Skipped automatically when no Gateway is reachable (so CI / machines without
Crew stay green). This is the productized version of the spike's connection +
PULL checks.

Run with a live Gateway:
    KIROWHISPER_RUN_INTEGRATION=1 pytest tests/test_gateway_integration.py -v
"""

from __future__ import annotations

import os
import socket

import pytest

from kirowhisper.config import GatewayConfig, load_config
from kirowhisper.gateway_client import GatewayClient

RUN = os.environ.get("KIROWHISPER_RUN_INTEGRATION") == "1"


def _gateway_reachable(cfg: GatewayConfig) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(cfg.base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 80
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not RUN, reason="integration test opt-in: set KIROWHISPER_RUN_INTEGRATION=1"
)


async def test_get_status_live():
    cfg = load_config().gateway
    if not _gateway_reachable(cfg):
        pytest.skip(f"no Gateway at {cfg.base_url}")
    async with GatewayClient(cfg) as gw:
        status = await gw.get_status()
        assert isinstance(status, dict)
        # A live Gateway reports uptime and session count.
        assert "uptime" in status or "sessions" in status


async def test_list_pending_approvals_live():
    cfg = load_config().gateway
    if not _gateway_reachable(cfg):
        pytest.skip(f"no Gateway at {cfg.base_url}")
    async with GatewayClient(cfg) as gw:
        approvals = await gw.list_pending_approvals()
        # May be empty; we only assert the call succeeds and maps to a list.
        assert isinstance(approvals, list)
