"""Audit log for KiroWhisper decisions.

Every decision (approve / reject / auto-pass / auto-block) is appended to a local
JSONL file with a timestamp, request id, risk level, action, and reason. This is
the source of "I blocked 3 dangerous operations today" summaries and the
responsible-AI / human-in-the-loop delivery guarantee.

Security (NFR-1): secret-looking values are masked before writing; raw secrets
never reach the audit file.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .models import DecisionAction, RiskLevel

# Patterns that look like secrets/credentials — masked before persisting.
_SECRET_PATTERNS = [
    re.compile(r"(?i)((?:aws_secret_access_key|secret_key|api[_-]?key|token|password|passwd|bearer)"
               r"\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)(\S+)"),
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),          # AWS access key id
    re.compile(r"\b(sk-[A-Za-z0-9]{16,})\b"),        # common secret-key prefix
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,})\b"), # GitHub tokens
]

_MASK = "***REDACTED***"


def mask_secrets(text: str) -> str:
    """Replace secret-looking substrings with a redaction marker."""
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        if pat.groups >= 2:
            out = pat.sub(lambda m: m.group(1) + _MASK, out)
        else:
            out = pat.sub(_MASK, out)
    return out


@dataclass(frozen=True)
class AuditEntry:
    """A single recorded decision."""

    ts: float
    approval_id: str
    risk: RiskLevel
    action: DecisionAction
    reason: str = ""
    by: str = "system"  # "system" (ambient) or "user" (voice decision)

    def to_json(self) -> str:
        d = asdict(self)
        d["risk"] = str(self.risk)
        d["action"] = str(self.action)
        d["reason"] = mask_secrets(self.reason)
        return json.dumps(d, ensure_ascii=False)


@dataclass(frozen=True)
class Digest:
    """What happened in a time window, for the spoken status ("while you were away")."""

    raised: int         # distinct approvals Crew asked for
    auto_passed: int    # passed silently as safe (session trust, rule-certain LOW)
    auto_blocked: int   # blocked silently by a catastrophic-operation rule
    you_approved: int   # approved by the user
    you_rejected: int   # rejected by the user


@dataclass
class AuditLog:
    """Append-only audit log backed by a JSONL file."""

    path: Path = field(default_factory=lambda: _default_path())
    # When this process started watching; the digest window for a first-ever check.
    started_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        approval_id: str,
        risk: RiskLevel,
        action: DecisionAction,
        reason: str = "",
        by: str = "system",
    ) -> AuditEntry:
        entry = AuditEntry(
            ts=time.time(),
            approval_id=approval_id,
            risk=risk,
            action=action,
            reason=reason,
            by=by,
        )
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(entry.to_json() + "\n")
        return entry

    def read_all(self) -> list[AuditEntry]:
        if not self.path.exists():
            return []
        entries: list[AuditEntry] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                entries.append(
                    AuditEntry(
                        ts=float(d["ts"]),
                        approval_id=str(d["approval_id"]),
                        risk=RiskLevel(d["risk"]),
                        action=DecisionAction(d["action"]),
                        reason=str(d.get("reason", "")),
                        by=str(d.get("by", "system")),
                    )
                )
            except (ValueError, KeyError):
                continue  # skip malformed lines rather than crash
        return entries

    def summary_since(self, since_ts: float = 0.0) -> dict[str, int]:
        """Count decisions by action since ``since_ts`` (for status summaries)."""
        counts = {a.value: 0 for a in DecisionAction}
        for e in self.read_all():
            if e.ts >= since_ts:
                counts[str(e.action)] = counts.get(str(e.action), 0) + 1
        return counts


    def digest_since(self, since_ts: float) -> Digest:
        """Summarize the audit log from ``since_ts`` on, counting each approval once.

        System entries are Ambient's own handling (every approval it saw gets one:
        surfaced, auto-passed or auto-blocked); user entries are voice decisions.
        Counting distinct approval ids keeps a surfaced-then-trusted step from being
        counted twice.
        """
        raised: set[str] = set()
        passed: set[str] = set()
        blocked: set[str] = set()
        approved: set[str] = set()
        rejected: set[str] = set()
        for e in self.read_all():
            if e.ts < since_ts:
                continue
            if e.by == "user":
                if e.action == DecisionAction.AUTO_APPROVE:
                    approved.add(e.approval_id)
                elif e.action == DecisionAction.AUTO_BLOCK:
                    rejected.add(e.approval_id)
                continue
            raised.add(e.approval_id)
            if e.action == DecisionAction.AUTO_APPROVE:
                passed.add(e.approval_id)
            elif e.action == DecisionAction.AUTO_BLOCK:
                blocked.add(e.approval_id)
        return Digest(len(raised), len(passed), len(blocked), len(approved), len(rejected))

    # ── "since you last checked" checkpoint (persists across restarts) ──

    @property
    def _checkpoint_path(self) -> Path:
        return self.path.with_suffix(".checkpoint")

    def last_status_check(self) -> float | None:
        """When the user last heard a status, or None if they never have."""
        try:
            return float(self._checkpoint_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    def mark_status_check(self, ts: float | None = None) -> None:
        self._checkpoint_path.write_text(str(ts if ts is not None else time.time()),
                                         encoding="utf-8")


def _default_path() -> Path:
    home = Path.home() / ".kiro" / "crew"
    base = home if home.exists() else Path.cwd()
    return base / "kirowhisper_audit.jsonl"
