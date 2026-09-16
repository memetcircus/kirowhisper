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


@dataclass
class AuditLog:
    """Append-only audit log backed by a JSONL file."""

    path: Path = field(default_factory=lambda: _default_path())

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


def _default_path() -> Path:
    home = Path.home() / ".kiro" / "crew"
    base = home if home.exists() else Path.cwd()
    return base / "kirowhisper_audit.jsonl"
