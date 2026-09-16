"""Summarizer — turns raw data into voice-friendly text.

Uses Amazon Bedrock for natural phrasing, but ALWAYS has a deterministic fallback
so the voice experience never goes silent when Bedrock is unavailable (NFR-2).

Output constraints (NFR-3): short, priority-ordered, not raw diff/log, secrets
masked, at most 2-3 options.
"""

from __future__ import annotations

from .audit import mask_secrets
from .config import BedrockConfig
from .models import Approval, RiskAssessment, RiskLevel

_SUMMARY_SYSTEM = (
    "You turn a software agent's pending action into ONE short spoken sentence for "
    "a developer who is not looking at a screen. Be concrete and decision-oriented: "
    "say what changes and whether it is reversible. No code, no diff, no markdown. "
    "Max 20 words. If risk is high, lead with the danger."
)


class Summarizer:
    """Produces voice-friendly summaries. Bedrock optional; fallback always works."""

    def __init__(self, config: BedrockConfig, *, bedrock_client=None) -> None:
        self._cfg = config
        self._client = bedrock_client  # a bedrock-runtime client, or None

    # ── approval summary ──

    def approval_summary(self, approval: Approval, risk: RiskAssessment) -> str:
        """One spoken sentence describing a pending approval and its risk."""
        # If the risk layer already produced a spoken summary, prefer it.
        if risk.spoken_summary:
            return _clip(mask_secrets(risk.spoken_summary))

        if self._client is not None:
            spoken = self._try_bedrock(approval, risk)
            if spoken:
                return _clip(mask_secrets(spoken))

        return _clip(mask_secrets(self._fallback_approval(approval, risk)))

    def _try_bedrock(self, approval: Approval, risk: RiskAssessment) -> str | None:
        prompt = (
            f"Risk: {risk.level}. Reason: {risk.reason}.\n"
            f"Tool: {approval.tool_title}\nPurpose: {approval.purpose}\n"
            f"Change:\n{approval.diff[:2000]}"
        )
        try:
            resp = self._client.converse(
                modelId=self._cfg.fast_model_id,
                system=[{"text": _SUMMARY_SYSTEM}],
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 80, "temperature": 0.2},
            )
            return resp["output"]["message"]["content"][0]["text"].strip()
        except Exception:  # noqa: BLE001 - fallback covers any failure
            return None

    @staticmethod
    def _fallback_approval(approval: Approval, risk: RiskAssessment) -> str:
        title = approval.tool_title or "an operation"
        lines_changed = _count_changed_lines(approval.diff)
        if risk.level == RiskLevel.HIGH:
            danger = risk.reason or "high-risk operation"
            tail = f", {lines_changed} lines" if lines_changed else ""
            return f"Careful: {title}{tail}. {danger}. This may be irreversible."
        if risk.level == RiskLevel.LOW:
            return f"{title}: low risk, reversible."
        tail = f", {lines_changed} lines" if lines_changed else ""
        return f"{title}{tail}. I'm not sure how risky this is, so I'm asking you."

    # ── status / ambient summary ──

    def status_summary(self, *, done: int, pending: int, failed: int = 0) -> str:
        """A standup-style status line."""
        parts = []
        if done:
            parts.append(f"{done} {'task' if done == 1 else 'tasks'} done")
        if failed:
            parts.append(f"{failed} failed")
        if pending:
            parts.append(f"{pending} waiting for you")
        if not parts:
            return "Nothing running right now."
        return _join_spoken(parts) + "."

    def ambient_summary(self, *, auto_passed: int, blocked: int, surfaced: int) -> str:
        """How Ambient Awareness handled the noise (e.g. 'I passed 19...')."""
        parts = []
        if auto_passed:
            parts.append(f"passed {auto_passed} as safe")
        if blocked:
            parts.append(f"blocked {blocked}")
        if surfaced:
            parts.append(f"{surfaced} waiting for you")
        if not parts:
            return "No decisions to report."
        return "I " + _join_spoken(parts) + "."


# ── helpers ──

def _clip(text: str, max_words: int = 28) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).rstrip(".,") + "."


def _count_changed_lines(diff: str) -> int:
    if not diff:
        return 0
    return sum(
        1 for ln in diff.splitlines()
        if (ln.startswith("+") or ln.startswith("-"))
        and not ln.startswith(("+++", "---"))
    )


def _join_spoken(parts: list[str]) -> str:
    """Join with commas and a final 'and', voice-friendly."""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"
