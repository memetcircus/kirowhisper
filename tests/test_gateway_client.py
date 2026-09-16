"""Unit tests for GatewayClient using httpx.MockTransport (no real Gateway).

Locks in the spike-verified contract: ?token= query + Origin header, and the
critical action="approved" (past tense) resolve body.
"""

from __future__ import annotations

import json

import httpx
import pytest

from kirowhisper.config import GatewayConfig
from kirowhisper.gateway_client import (
    ACTION_APPROVE,
    ACTION_REJECT,
    ACTION_TRUST,
    GatewayClient,
    GatewayError,
)

BASE = "http://localhost:5476"


def _cfg() -> GatewayConfig:
    # Explicit token so the client never shells out to `kirocrew token` in tests.
    return GatewayConfig(base_url=BASE, token="TESTTOKEN")


def _client(handler) -> GatewayClient:
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return GatewayClient(_cfg(), http=http)


# ── auth: token as query param + Origin header ──

async def test_auth_token_query_and_origin_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.url.params.get("token")
        seen["origin"] = request.headers.get("origin")
        return httpx.Response(200, json={"uptime": "1m"})

    gw = _client(handler)
    await gw.get_status()
    await gw.aclose()

    assert seen["token"] == "TESTTOKEN"          # sent as query param
    assert seen["origin"] == BASE                # Origin header required by Gateway


# ── resolve: the action="approved" gotcha ──

async def test_approve_sends_past_tense_action():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    gw = _client(handler)
    res = await gw.approve("slot1", "req-123")
    await gw.aclose()

    assert res == {"ok": True}
    assert captured["path"] == "/api/chat/slots/slot1/approve"
    assert captured["body"]["action"] == "approved"   # NOT "approve"
    assert captured["body"]["action"] == ACTION_APPROVE
    assert captured["body"]["request_id"] == "req-123"


async def test_reject_and_trust_actions():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    gw = _client(handler)
    await gw.reject("s", "r")
    assert captured["body"]["action"] == ACTION_REJECT == "rejected"
    await gw.trust_slot("s", "r")
    assert captured["body"]["action"] == ACTION_TRUST == "trust"
    await gw.aclose()


async def test_resolve_rejects_invalid_action():
    gw = _client(lambda r: httpx.Response(200, json={}))
    with pytest.raises(GatewayError):
        await gw.resolve("s", "r", "approve")  # wrong tense -> must be rejected early
    await gw.aclose()


# ── list_pending_approvals -> Approval mapping ──

async def test_list_pending_approvals_maps_entries():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[
            {"id": "spawn:a1", "tool": "spawn_run(x)", "tool_purpose": "p", "slot": "", "ts": 1.0},
            {"id": "spawn:a2", "tool": "edit(y)", "tool_purpose": "q", "slot": "s2", "ts": 2.0},
        ])

    gw = _client(handler)
    approvals = await gw.list_pending_approvals()
    await gw.aclose()

    assert len(approvals) == 2
    assert approvals[0].request_id == "spawn:a1"
    assert approvals[0].tool_title == "spawn_run(x)"
    assert approvals[1].slot == "s2"


# ── get_slot_pending_approval reads role=='permission' meta ──

async def test_get_slot_pending_approval_from_permission_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "messages": [
                {"role": "user", "content": "do it"},
                {"role": "tool", "content": "Creating x", "meta": {"purpose": "make x"}},
                {"role": "permission", "content": "Creating x.txt", "meta": {
                    "approval_id": "perm-9", "tool_title": "Creating x.txt",
                    "tool_input": "+++ x", "is_read_only": "", "is_shell": "",
                }},
            ]
        })

    gw = _client(handler)
    approval = await gw.get_slot_pending_approval("slotZ")
    await gw.aclose()

    assert approval is not None
    assert approval.request_id == "perm-9"
    assert approval.tool_title == "Creating x.txt"
    assert approval.is_read_only is False
    assert approval.is_shell is False


async def test_get_slot_pending_approval_returns_none_when_no_permission():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"messages": [{"role": "user", "content": "hi"}]})

    gw = _client(handler)
    assert await gw.get_slot_pending_approval("s") is None
    await gw.aclose()


# ── error handling ──

async def test_403_raises_gateway_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "Token required", "code": "forbidden"})

    gw = _client(handler)
    with pytest.raises(GatewayError):
        await gw.get_status()
    await gw.aclose()


async def test_transport_error_raises_gateway_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    gw = _client(handler)
    with pytest.raises(GatewayError):
        await gw.get_status()
    await gw.aclose()


async def test_empty_body_returns_empty_dict():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="")

    gw = _client(handler)
    assert await gw.get_status() == {}
    await gw.aclose()


# ── spawn returns id ──

async def test_spawn_returns_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "task-77", "status": "spawned"})

    gw = _client(handler)
    assert await gw.spawn("do work") == "task-77"
    await gw.aclose()
