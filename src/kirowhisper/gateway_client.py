"""Kiro Crew Gateway REST client.

Thin, single-responsibility wrapper over the real Gateway API, verified live in
the spike (see the private working notes -> "Crew Spike Results").

Auth model (spike-verified):
  - token comes from ``kirocrew token`` (a JWT), passed as query param ``?token=``
  - every request MUST carry an ``Origin`` header equal to the base URL, or the
    Gateway's ``deny_non_dashboard_caller`` returns 403.

Critical gotcha (spike-verified): to APPROVE, the action string must be
``"approved"`` (past tense). Sending ``"approve"`` silently resolves to rejected.
"""

from __future__ import annotations

import asyncio
import shlex
import subprocess
from typing import Any

import httpx

from .config import GatewayConfig
from .models import Approval


class GatewayError(RuntimeError):
    """Raised when a Gateway request fails."""


class ApprovalNotPendingError(GatewayError):
    """Raised when an approval expired or was resolved before this action."""


# Action strings the Gateway's approve endpoint understands (spike-verified).
ACTION_APPROVE = "approved"   # past tense — NOT "approve"
ACTION_REJECT = "rejected"
ACTION_TRUST = "trust"        # auto-approve remaining tools in the slot


class GatewayClient:
    """Async client for the Kiro Crew Gateway.

    Usage::

        async with GatewayClient(cfg) as gw:
            status = await gw.get_status()
            pending = await gw.list_pending_approvals()
    """

    def __init__(self, config: GatewayConfig, *, http: httpx.AsyncClient | None = None) -> None:
        self._cfg = config
        self._token: str = config.token
        self._external_http = http is not None
        self._http = http or httpx.AsyncClient(timeout=config.request_timeout_s)

    async def __aenter__(self) -> GatewayClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if not self._external_http:
            await self._http.aclose()

    # ── auth ──

    def _fetch_token(self) -> str:
        """Run the token command and extract the JWT after 'token='."""
        cmd = self._cfg.token_command
        try:
            out = subprocess.check_output(shlex.split(cmd), text=True, timeout=15).strip()
        except (subprocess.SubprocessError, OSError) as exc:
            raise GatewayError(f"token command failed: {cmd!r}: {exc}") from exc
        if "token=" not in out:
            raise GatewayError(f"token command output had no token=: {out[:80]!r}")
        return out.split("token=", 1)[1].strip()

    def _ensure_token(self) -> str:
        if not self._token:
            self._token = self._fetch_token()
        return self._token

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params = {"token": self._ensure_token()}
        if extra:
            params.update(extra)
        return params

    @property
    def _headers(self) -> dict[str, str]:
        # Origin MUST equal base_url or the Gateway refuses (deny_non_dashboard_caller).
        return {"Origin": self._cfg.origin, "Content-Type": "application/json"}

    # ── request core ──

    async def _get(self, path: str) -> Any:
        return await self._request("GET", path)

    async def _post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return await self._request("POST", path, body)

    async def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        url = f"{self._cfg.base_url.rstrip('/')}{path}"
        try:
            resp = await self._http.request(
                method, url, params=self._params(), headers=self._headers, json=body
            )
        except httpx.HTTPError as exc:
            raise GatewayError(f"{method} {path} transport error: {exc}") from exc
        if resp.status_code == 403:
            raise GatewayError(f"{method} {path} forbidden (auth/origin?): {resp.text[:120]}")
        if resp.status_code >= 400:
            raise GatewayError(f"{method} {path} HTTP {resp.status_code}: {resp.text[:120]}")
        text = resp.text.strip()
        if not text:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {"raw": text}

    # ── endpoints (spike-verified) ──

    async def get_status(self) -> dict[str, Any]:
        """GET /api/status — uptime, sessions, subagents, etc."""
        return await self._get("/api/status")

    async def list_pending_approvals(self) -> list[Approval]:
        """All pending approvals from BOTH sources, de-duplicated by request_id.

        Two places carry pending approvals (verified live):
          - ``GET /api/approvals`` — mostly subagent/background approvals.
          - each chat slot's ``role:"permission"`` message — interactive chat/task
            approvals that do NOT appear in /api/approvals.
        The ambient engine needs both, so we merge them.
        """
        found: dict[str, Approval] = {}

        raw = await self._get("/api/approvals")
        for entry in raw if isinstance(raw, list) else []:
            ap = Approval.from_approvals_entry(entry)
            if ap.request_id:
                found[ap.request_id] = ap

        for slot in await self.list_slots():
            ap = await self.get_slot_pending_approval(slot)
            if ap is not None and ap.request_id not in found:
                found[ap.request_id] = ap

        return list(found.values())

    async def list_slots(self) -> list[str]:
        """GET /api/chat/slots — the keys of all active chat slots."""
        raw = await self._get("/api/chat/slots")
        if isinstance(raw, list):
            slots = raw
        elif isinstance(raw, dict):
            slots = raw.get("slots", [])
        else:
            slots = []
        keys: list[str] = []
        for s in slots:
            if isinstance(s, dict):
                key = s.get("key") or s.get("name")
                if key:
                    keys.append(str(key))
            elif isinstance(s, str):
                keys.append(s)
        return keys

    async def get_slot(self, slot: str) -> dict[str, Any]:
        """GET /api/chat/slots/<slot> — full slot object incl. messages."""
        return await self._get(f"/api/chat/slots/{slot}")

    async def get_slot_pending_approval(self, slot: str) -> Approval | None:
        """Extract the most recent UNRESOLVED permission approval from a slot.

        The reliable signal (verified live) is a message with role=='permission'
        carrying meta.approval_id AND an empty meta.resolved. A permission whose
        meta.resolved is set (e.g. "approved"/"rejected"/"stale") is already
        handled and must NOT be surfaced again, or approving it 404s with
        "no pending approval".
        """
        slot_obj = await self.get_slot(slot)
        messages = slot_obj.get("messages", [])
        for msg in reversed(messages):
            if msg.get("role") == "permission":
                meta = msg.get("meta", {}) or {}
                if str(meta.get("resolved") or "").strip():
                    continue  # already resolved -> not pending
                approval = Approval.from_permission_meta(slot, msg.get("content", ""), meta)
                if approval.request_id:
                    return approval
        return None

    async def get_slot_approval_status(self, slot: str, request_id: str) -> str:
        """Return the exact permission's current state from the slot history.

        ``pending`` means the permission exists and has no ``meta.resolved``
        value. Other values are normalized Gateway resolution states such as
        ``approved``, ``rejected`` or ``stale``. ``missing`` is fail-closed:
        callers must not treat an unknown approval as actionable.
        """
        if not slot:
            return "missing"
        slot_obj = await self.get_slot(slot)
        messages = slot_obj.get("messages", [])
        for msg in reversed(messages):
            if msg.get("role") != "permission":
                continue
            meta = msg.get("meta", {}) or {}
            approval_id = str(meta.get("approval_id") or meta.get("request_id") or "")
            if approval_id != request_id:
                continue
            resolved = str(meta.get("resolved") or "").strip().lower()
            return resolved or "pending"
        return "missing"

    async def resolve(self, slot: str, request_id: str, action: str) -> dict[str, Any]:
        """Resolve a pending approval and verify the resulting slot state.

        The Gateway may return HTTP 200 / ``{"ok": true}`` even when a racing
        deny-on-silence timeout already handled the permission. For approve and
        reject, success therefore means the exact permission's
        ``meta.resolved`` value matches the requested action after the POST.
        """
        if action not in (ACTION_APPROVE, ACTION_REJECT, ACTION_TRUST):
            raise GatewayError(f"invalid resolve action: {action!r}")

        # Trust applies to a slot rather than one exact permission and has no
        # stable per-permission postcondition in the observed Gateway contract.
        if action == ACTION_TRUST:
            return await self._post(
                f"/api/chat/slots/{slot}/approve",
                {"action": action, "request_id": request_id},
            )

        before = await self.get_slot_approval_status(slot, request_id)
        if before != "pending":
            raise ApprovalNotPendingError(
                f"approval {request_id} is no longer pending (state: {before})"
            )

        result = await self._post(
            f"/api/chat/slots/{slot}/approve",
            {"action": action, "request_id": request_id},
        )

        # Slot state is normally updated synchronously. Allow two short retries
        # for propagation without spending a meaningful part of Alexa's budget.
        for attempt in range(3):
            after = await self.get_slot_approval_status(slot, request_id)
            if after == action:
                return result
            if after != "pending":
                raise ApprovalNotPendingError(
                    f"approval {request_id} resolved as {after}, not {action}"
                )
            if attempt < 2:
                await asyncio.sleep(0.05)

        raise GatewayError(
            f"approval {request_id} did not resolve as {action}; it is still pending"
        )

    async def approve(self, slot: str, request_id: str) -> dict[str, Any]:
        return await self.resolve(slot, request_id, ACTION_APPROVE)

    async def reject(self, slot: str, request_id: str) -> dict[str, Any]:
        return await self.resolve(slot, request_id, ACTION_REJECT)

    async def trust_slot(self, slot: str, request_id: str) -> dict[str, Any]:
        return await self.resolve(slot, request_id, ACTION_TRUST)

    async def create_slot(self, name: str) -> dict[str, Any]:
        return await self._post("/api/chat/slots", {"name": name})

    async def send_message(self, slot: str, message: str) -> None:
        """POST /api/chat — long-lived (may block on tool approval).

        Fire-and-don't-wait: we intentionally do not await a full response, since
        the turn can pause waiting for approval. Callers poll for state instead.
        """
        url = f"{self._cfg.base_url.rstrip('/')}/api/chat"
        try:
            await self._http.request(
                "POST", url,
                params=self._params(),
                headers=self._headers,
                json={"slot": slot, "message": message},
                timeout=2.0,
            )
        except httpx.HTTPError:
            # Expected: the request may not return promptly. The message is queued.
            pass

    async def spawn(self, task: str) -> str:
        """POST /api/spawn — start a background subagent task. Returns task id."""
        res = await self._post("/api/spawn", {"task": task})
        return str(res.get("id", ""))

    async def get_task_result(self, task_id: str) -> dict[str, Any]:
        """GET /api/spawn/<id> — task state (done, turns, awaiting_approval, ...)."""
        return await self._get(f"/api/spawn/{task_id}")
