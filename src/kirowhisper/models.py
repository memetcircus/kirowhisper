"""Core data models for KiroWhisper.

These mirror the real Kiro Crew Gateway shapes observed during the spike
(see docs/PROJECT_NOTES.md) plus KiroWhisper's own risk/decision layer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    """Risk classification of an approval. Security tightens one way only."""

    LOW = "low"          # read-only / clearly reversible
    HIGH = "high"        # destructive / irreversible / shell / secret exposure
    UNKNOWN = "unknown"  # cannot be determined safely -> always surfaced


class DecisionAction(StrEnum):
    """What Ambient Awareness decided to do with an approval."""

    AUTO_APPROVE = "auto_approve"  # LOW + trusted -> silently approved
    AUTO_BLOCK = "auto_block"      # explicit deny rule -> silently rejected
    SURFACE = "surface"            # needs a real human decision -> brought to user


@dataclass(frozen=True)
class Approval:
    """A pending tool approval raised by Kiro Crew.

    Sourced from the Gateway ``role:"permission"`` message meta and/or
    ``GET /api/approvals``. ``request_id`` is what resolves the approval.
    """

    request_id: str
    slot: str
    tool_title: str
    purpose: str = ""
    diff: str = ""            # tool_input (e.g. a unified diff), possibly large
    is_read_only: bool = False
    is_shell: bool = False
    ts: float = field(default_factory=time.time)

    @classmethod
    def from_permission_meta(cls, slot: str, content: str, meta: dict[str, Any]) -> Approval:
        """Build from a Gateway permission message (role=='permission')."""
        return cls(
            request_id=str(meta.get("approval_id") or meta.get("request_id") or ""),
            slot=slot,
            tool_title=str(meta.get("tool_title") or content or ""),
            purpose=str(meta.get("purpose") or ""),
            diff=str(meta.get("tool_input") or ""),
            is_read_only=_truthy(meta.get("is_read_only")),
            is_shell=_truthy(meta.get("is_shell")),
        )

    @classmethod
    def from_approvals_entry(cls, entry: dict[str, Any]) -> Approval:
        """Build from a ``GET /api/approvals`` list entry."""
        raw_id = str(entry.get("id") or "")
        # /api/approvals ids look like "spawn:<id>"; keep the raw id, strip prefix
        # only for display purposes elsewhere.
        return cls(
            request_id=raw_id,
            slot=str(entry.get("slot") or ""),
            tool_title=str(entry.get("tool") or ""),
            purpose=str(entry.get("tool_purpose") or ""),
            diff=str(entry.get("tool_input") or ""),
            ts=float(entry.get("ts") or time.time()),
        )


@dataclass(frozen=True)
class RiskAssessment:
    """Result of classifying an approval."""

    level: RiskLevel
    reason: str = ""
    spoken_summary: str = ""


@dataclass(frozen=True)
class Decision:
    """What Ambient Awareness did with an approval."""

    approval_id: str
    action: DecisionAction
    risk: RiskLevel
    reason: str = ""
    ts: float = field(default_factory=time.time)


@dataclass
class PendingDecision:
    """An approval surfaced to the user, awaiting their voice decision."""

    approval: Approval
    risk: RiskAssessment
    surfaced_at: float = field(default_factory=time.time)


def _truthy(value: Any) -> bool:
    """Gateway sometimes sends '' / '0' / 'false' for booleans; normalize."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    s = str(value).strip().lower()
    return s not in ("", "0", "false", "no", "none")
