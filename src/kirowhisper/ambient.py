"""Ambient Awareness engine — the heart of KiroWhisper.

A background async loop that watches Crew's pending approvals, classifies each by
risk, and routes it into one of three buckets:
  - AUTO_APPROVE (LOW + trust) -> silently approve via the Gateway
  - AUTO_BLOCK (explicit deny)  -> silently reject via the Gateway
  - SURFACE (HIGH/UNKNOWN/etc.) -> queue for the user + fire a proactive callback

Design guarantees:
  - Idempotent: each approval id is processed once.
  - Conservative: HIGH/UNKNOWN always surface (via policy.decide).
  - Fail-safe: if the Gateway is unreachable, nothing is auto-passed (R1.4); the
    loop retries with capped backoff and never fabricates a decision.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from .audit import AuditLog
from .config import AmbientConfig
from .gateway_client import GatewayClient, GatewayError
from .models import (
    Approval,
    Decision,
    DecisionAction,
    PendingDecision,
    RiskAssessment,
    RiskLevel,
)
from .policy import decide
from .risk import RiskClassifier

# A callback invoked when a decision is surfaced to the user (proactive alert).
SurfaceCallback = Callable[[PendingDecision], Awaitable[None]] | None


class AmbientEngine:
    """Watches approvals and applies the three-bucket policy."""

    def __init__(
        self,
        gateway: GatewayClient,
        classifier: RiskClassifier,
        audit: AuditLog,
        config: AmbientConfig,
        *,
        session_trust: bool = False,
        deny_check: Callable[[Approval], bool] | None = None,
        on_surface: SurfaceCallback = None,
    ) -> None:
        self._gw = gateway
        self._classifier = classifier
        self._audit = audit
        self._cfg = config
        self._session_trust = session_trust
        self._deny_check = deny_check or (lambda _a: False)
        self._on_surface = on_surface

        self._seen: set[str] = set()
        self._pending: dict[str, PendingDecision] = {}
        self._counts = {a.value: 0 for a in DecisionAction}
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # ── lifecycle ──

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self.poll_once()
                backoff = 1.0  # reset after a successful poll
                await asyncio.sleep(self._cfg.poll_interval_s)
            except GatewayError:
                # Fail-safe: Gateway unreachable -> retry, auto-pass nothing.
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._cfg.max_backoff_s)

    # ── one polling cycle (also directly callable in tests) ──

    async def poll_once(self) -> list[Decision]:
        """Fetch pending approvals, classify + route the new ones. Returns decisions made."""
        approvals = await self._gw.list_pending_approvals()
        live_ids = {a.request_id for a in approvals}

        # Drop stale entries: if a surfaced decision's underlying Crew slot/approval
        # is gone (deleted, expired, or resolved outside our own approve/reject
        # calls), the Gateway simply stops listing it. Without this, _pending would
        # accumulate ghost entries forever and get_pending_decisions would report a
        # growing, wrong count (observed live: "6 decisions waiting" with 1 real).
        stale = [rid for rid in self._pending if rid not in live_ids]
        for rid in stale:
            self._pending.pop(rid, None)
            self._seen.discard(rid)  # allow it to be re-surfaced if it reappears

        decisions: list[Decision] = []
        for approval in approvals:
            if approval.request_id in self._seen:
                continue
            self._seen.add(approval.request_id)
            decisions.append(await self._handle(approval))
        return decisions

    async def _handle(self, approval: Approval) -> Decision:
        risk: RiskAssessment = self._classifier.classify(approval)
        action, reason = decide(
            risk,
            session_trust=self._session_trust,
            explicit_deny=self._deny_check(approval),
        )

        if action == DecisionAction.AUTO_APPROVE:
            await self._safe_resolve(approval, risk, approved=True)
        elif action == DecisionAction.AUTO_BLOCK:
            await self._safe_resolve(approval, risk, approved=False)
        else:  # SURFACE
            pending = PendingDecision(approval=approval, risk=risk)
            self._pending[approval.request_id] = pending
            if self._on_surface is not None:
                await self._on_surface(pending)

        self._counts[action.value] += 1
        self._audit.record(approval.request_id, risk.level, action, reason)
        return Decision(approval.request_id, action, risk.level, reason)

    async def _safe_resolve(
        self, approval: Approval, risk: RiskAssessment, *, approved: bool
    ) -> None:
        """Resolve on the Gateway; a resolve failure must not crash the loop."""
        try:
            if approved:
                await self._gw.approve(approval.slot, approval.request_id)
            else:
                await self._gw.reject(approval.slot, approval.request_id)
        except GatewayError:
            # If we cannot apply an auto decision, drop it back to pending so the
            # user still sees it (never silently swallow).
            self._pending[approval.request_id] = PendingDecision(approval=approval, risk=risk)

    # ── read APIs (for status summaries / the MCP layer) ──

    def pending_decisions(self) -> list[PendingDecision]:
        """Surfaced approvals awaiting the user, newest last."""
        return sorted(self._pending.values(), key=lambda p: p.surfaced_at)

    def take_pending(self, request_id: str) -> PendingDecision | None:
        """Remove and return a surfaced decision once the user acts on it."""
        return self._pending.pop(request_id, None)

    def requeue(self, pending: PendingDecision) -> None:
        """Put a surfaced decision back (e.g. awaiting confirmation or a failed resolve)."""
        self._pending[pending.approval.request_id] = pending

    def set_session_trust(self, trust: bool) -> None:
        """Enable/disable auto-approval of low-risk steps for this session.

        Note: this only changes how *future* approvals are routed. To also clear
        low-risk items already surfaced, call ``apply_trust_to_pending``.
        """
        self._session_trust = trust

    async def apply_trust_to_pending(self) -> int:
        """Retroactively auto-approve already-surfaced LOW decisions under trust.

        When the user says "trust" mid-session, the low-risk items already waiting
        should clear silently too — otherwise trust would only affect brand-new
        approvals and the queue would stay noisy. HIGH/UNKNOWN always stay.
        Returns the number of pending items auto-approved.
        """
        if not self._session_trust:
            return 0
        cleared = 0
        for rid, pending in list(self._pending.items()):
            action, _reason = decide(
                pending.risk,
                session_trust=True,
                explicit_deny=self._deny_check(pending.approval),
            )
            if action != DecisionAction.AUTO_APPROVE:
                continue  # HIGH / UNKNOWN stay surfaced — trust never lowers safety
            # Remove first; _safe_resolve puts it back only if the Gateway fails.
            self._pending.pop(rid, None)
            await self._safe_resolve(pending.approval, pending.risk, approved=True)
            if rid in self._pending:
                continue  # resolve failed and was re-queued -> leave it surfaced
            self._counts[DecisionAction.AUTO_APPROVE.value] += 1
            # by="system": the user granted trust, but this specific step was passed
            # automatically, so it counts as "I passed it as safe" in the digest.
            self._audit.record(rid, pending.risk.level, DecisionAction.AUTO_APPROVE,
                               "trust granted mid-session", by="system")
            cleared += 1
        return cleared

    async def approve_pending_safe(self) -> tuple[int, int]:
        """One-shot: approve every rule-certain LOW decision waiting right now.

        This is "approve all the safe ones" WITHOUT flipping on session trust: it
        clears the currently-waiting safe steps but does not change how future
        approvals are routed. The safety bar is identical to trust — only a
        deterministic (rule-certain) LOW is approved; HIGH, UNKNOWN, and a
        model-guessed LOW are left surfaced, untouched. A catastrophic step (deny
        rule) is also left for the user, never silently approved here.

        Returns (approved, remaining): how many were cleared, and how many are
        still waiting for the user afterwards.
        """
        approved = 0
        for rid, pending in list(self._pending.items()):
            # Never batch-approve something a deny rule would block.
            if self._deny_check(pending.approval):
                continue
            # Only rule-certain LOW clears — same gate the policy uses under trust.
            if not (pending.risk.level == RiskLevel.LOW and pending.risk.deterministic):
                continue
            self._pending.pop(rid, None)
            await self._safe_resolve(pending.approval, pending.risk, approved=True)
            if rid in self._pending:
                continue  # resolve failed and was re-queued -> leave it surfaced
            self._counts[DecisionAction.AUTO_APPROVE.value] += 1
            self._audit.record(rid, pending.risk.level, DecisionAction.AUTO_APPROVE,
                               "user approved all safe (voice, batch)", by="user")
            approved += 1
        return approved, len(self._pending)

    def set_on_surface(self, callback: SurfaceCallback) -> None:
        """Register the proactive callback fired when a decision is surfaced."""
        self._on_surface = callback

    def snapshot(self) -> dict[str, int]:
        """Counts by action since start (source of the ambient summary)."""
        snap = dict(self._counts)
        snap["pending"] = len(self._pending)
        return snap
