"""JSON HTTP bridge for the voice simulation UI.

The browser cannot speak MCP directly, so this bridge exposes plain JSON endpoints
that call the SAME core services the MCP tools do (Ambient engine + Gateway +
Summarizer). This keeps the intelligence in one place; the bridge is just a thin
web adapter for the simulated voice front-end.

Endpoints (all JSON):
  GET  /api/status    -> spoken status + ambient snapshot
  GET  /api/pending   -> surfaced decisions (voice-friendly), newest/high-risk first
  POST /api/approve   -> {request_id, confirmed?} approve a surfaced decision
  POST /api/reject    -> {request_id} reject (skip) a surfaced decision
  POST /api/trust     -> enable session trust
  GET  /events        -> Server-Sent Events stream of proactive surfaces
  GET  /              -> the single-page voice UI
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

from ..gateway_client import GatewayError
from ..mcp_server import KiroWhisperServices
from ..models import DecisionAction, PendingDecision, RiskLevel

_STATIC = Path(__file__).parent / "static"


class VoiceBridge:
    """Wraps the core services and exposes them as a JSON web app."""

    def __init__(self, services: KiroWhisperServices) -> None:
        self._svc = services
        self._surface_queue: asyncio.Queue[str] = asyncio.Queue()
        # Register a proactive callback so surfaced decisions push to the SSE stream.
        self._svc.ambient.set_on_surface(self._on_surface)

    async def _on_surface(self, pending: PendingDecision) -> None:
        spoken = self._svc.summarizer.approval_summary(pending.approval, pending.risk)
        await self._surface_queue.put(
            json.dumps({"request_id": pending.approval.request_id, "spoken": spoken})
        )

    # ── handlers ──

    async def index(self, _request: Request):
        return FileResponse(_STATIC / "index.html")

    async def status(self, _request: Request):
        snap = self._svc.ambient.snapshot()
        try:
            gw = await self._svc.gateway.get_status()
        except GatewayError:
            gw = {}
        spoken = self._svc.summarizer.ambient_summary(
            auto_passed=snap.get(DecisionAction.AUTO_APPROVE.value, 0),
            blocked=snap.get(DecisionAction.AUTO_BLOCK.value, 0),
            surfaced=snap.get("pending", 0),
        )
        return JSONResponse({"spoken": spoken, "snapshot": snap, "sessions": gw.get("sessions")})

    async def pending(self, _request: Request):
        pend = self._svc.ambient.pending_decisions()
        pend.sort(key=lambda p: 0 if p.risk.level == RiskLevel.HIGH else 1)
        items = [
            {
                "request_id": p.approval.request_id,
                "risk": str(p.risk.level),
                "spoken": self._svc.summarizer.approval_summary(p.approval, p.risk),
            }
            for p in pend
        ]
        return JSONResponse({"pending": items})

    async def approve(self, request: Request):
        body = await _json(request)
        rid = body.get("request_id", "")
        confirmed = bool(body.get("confirmed", False))
        pending = self._svc.ambient.take_pending(rid)
        if pending is None:
            return JSONResponse({"spoken": "I couldn't find that decision.", "ok": False})
        if pending.risk.level == RiskLevel.HIGH and not confirmed:
            self._svc.ambient.requeue(pending)
            spoken = self._svc.summarizer.approval_summary(pending.approval, pending.risk)
            return JSONResponse(
                {"spoken": f"{spoken} This is high-risk. Confirm to proceed.",
                 "ok": False, "needs_confirmation": True}
            )
        try:
            await self._svc.gateway.approve(pending.approval.slot, rid)
        except GatewayError as exc:
            self._svc.ambient.requeue(pending)
            return JSONResponse({"spoken": f"I couldn't apply it: {exc}", "ok": False})
        self._svc.audit.record(rid, pending.risk.level, DecisionAction.AUTO_APPROVE,
                               "user approved", by="user")
        return JSONResponse({"spoken": "Approved. Continuing.", "ok": True})

    async def reject(self, request: Request):
        body = await _json(request)
        rid = body.get("request_id", "")
        pending = self._svc.ambient.take_pending(rid)
        if pending is None:
            return JSONResponse({"spoken": "I couldn't find that decision.", "ok": False})
        try:
            await self._svc.gateway.reject(pending.approval.slot, rid)
        except GatewayError as exc:
            self._svc.ambient.requeue(pending)
            return JSONResponse({"spoken": f"I couldn't apply it: {exc}", "ok": False})
        self._svc.audit.record(rid, pending.risk.level, DecisionAction.AUTO_BLOCK,
                               "user rejected", by="user")
        return JSONResponse({"spoken": "I didn't do it. The task can continue.", "ok": True})

    async def trust(self, _request: Request):
        self._svc.ambient.set_session_trust(True)
        return JSONResponse(
            {"spoken": "Session trusted. I'll auto-approve low-risk steps and still "
                       "ask about anything high-risk.", "ok": True}
        )

    async def events(self, _request: Request):
        async def stream():
            while True:
                msg = await self._surface_queue.get()
                yield f"data: {msg}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    def app(self) -> Starlette:
        return Starlette(routes=[
            Route("/", self.index),
            Route("/api/status", self.status),
            Route("/api/pending", self.pending),
            Route("/api/approve", self.approve, methods=["POST"]),
            Route("/api/reject", self.reject, methods=["POST"]),
            Route("/api/trust", self.trust, methods=["POST"]),
            Route("/events", self.events),
        ])


async def _json(request: Request) -> dict:
    try:
        return await request.json()
    except (ValueError, TypeError):
        return {}
