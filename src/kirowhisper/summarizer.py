"""Summarizer — turns raw data into voice-friendly text.

Uses Amazon Bedrock for natural phrasing, but ALWAYS has a deterministic fallback
so the voice experience never goes silent when Bedrock is unavailable (NFR-2).

Output constraints (NFR-3): short, priority-ordered, not raw diff/log, secrets
masked, at most 2-3 options.
"""

from __future__ import annotations

import re

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

    def approval_summary(
        self, approval: Approval, risk: RiskAssessment, *, fast: bool = False
    ) -> str:
        """One spoken sentence describing a pending approval and its risk.

        With ``fast=True`` the summary never calls Bedrock: it uses a pre-computed
        spoken line if the risk layer produced one, otherwise the deterministic
        fallback. This matters for latency-bound callers like the Alexa turn
        (a tool that elicits must return well inside the few seconds Alexa allows).
        """
        # If the risk layer already produced a spoken summary, prefer it (instant).
        if risk.spoken_summary:
            return _clip(mask_secrets(risk.spoken_summary))

        if not fast and self._client is not None:
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

    # ── explanation (the "why" layer) ──

    def explain(self, approval: Approval, risk: RiskAssessment) -> str:
        """A spoken explanation of a pending decision: what it is, WHY it carries
        the risk it does, and what happens if the user rejects it.

        Answers the follow-up questions a decision-maker asks out loud —
        "why is that risky?" and "what happens if I reject it?" — from the risk
        layer's own reasoning. Deterministic and fast (no Bedrock): it must return
        inside an Alexa turn, and it should say exactly what the guardrail decided,
        not a fresh model guess about the same command.
        """
        title = approval.tool_title or "this operation"
        # What it will do (mask any secrets that slipped into the command/diff).
        what = mask_secrets(approval.purpose.strip()) if approval.purpose else ""

        # Why this risk level. The risk layer's reason is a short noun phrase
        # ("shell command", "recursive/forced file removal"), so join it with
        # "because of" for natural speech. Fall back to a full clause per level.
        reason = mask_secrets(risk.reason.strip()) if risk.reason else ""
        # What rejecting does — same for every level: the step just doesn't run.
        reject = "If you reject it, that step won't run and the task continues past it."

        head = f"{title} — {what}" if what else title

        if risk.level == RiskLevel.HIGH:
            certainty = (
                "A safety rule flagged this as high risk"
                if risk.deterministic
                else "This looks high risk"
            )
            why = (
                f"because of {reason}" if reason
                else "because it looks destructive or hard to undo"
            )
            body = f"{certainty}: {head}. It's flagged {why}. It may not be reversible."
        elif risk.level == RiskLevel.LOW:
            certainty = (
                "A safety rule cleared this as low risk"
                if risk.deterministic
                else "This looks low risk"
            )
            because = f", because it's {reason}" if reason else ""
            body = f"{certainty}: {head}{because}. It's reversible."
        else:  # UNKNOWN
            why = (
                f"because {reason}" if reason
                else "because I couldn't classify it with confidence"
            )
            body = (
                f"I'm not sure how risky this is, so I'm asking you: {head}. "
                f"It's flagged {why}. I can't tell if it's reversible."
            )

        return _clip(f"{body} {reject}", max_words=60)

    # ── task health ("which one failed?" / "how are my tasks doing?") ──

    def task_health(self, slots: list[dict]) -> str:
        """Spoken answer to 'which task failed?' / 'how are my tasks doing?'.

        ``slots`` are the structured summaries from
        ``GatewayClient.list_slot_summaries`` (title, running, awaiting_approval,
        last_message). Crew gives no structured failure field, so each task's
        health is inferred from its last assistant message. We are deliberately
        honest in the wording: a task that mentions an error is described as
        having "reported a problem", not asserted as definitively broken.

        Troubled tasks are named FIRST (that is the question being asked), then a
        one-line roll-up of the rest.
        """
        if not slots:
            return "There are no active sessions right now."

        troubled: list[str] = []
        running: list[str] = []
        waiting: list[str] = []
        healthy = 0
        for s in slots:
            title = _short_title(str(s.get("title") or s.get("slot") or "a task"))
            if s.get("awaiting_approval"):
                waiting.append(title)
            elif s.get("running"):
                running.append(title)
            elif _looks_troubled(str(s.get("last_message") or "")):
                # Attach a short, masked reason drawn from the task's own words.
                reason = _trouble_reason(str(s.get("last_message") or ""))
                troubled.append(f"{title}" + (f" — {reason}" if reason else ""))
            else:
                healthy += 1

        parts: list[str] = []
        if troubled:
            noun = "task" if len(troubled) == 1 else "tasks"
            parts.append(
                f"{len(troubled)} {noun} reported a problem: "
                + _join_spoken(troubled) + "."
            )
        else:
            parts.append("Nothing has reported a failure.")

        roll: list[str] = []
        if running:
            roll.append(f"{len(running)} still running")
        if waiting:
            roll.append(f"{len(waiting)} waiting for your approval")
        if healthy:
            roll.append(f"{healthy} finished cleanly")
        if roll:
            parts.append(_join_spoken(roll).capitalize() + ".")
        return " ".join(parts)

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
        handled = []
        if auto_passed:
            handled.append(f"passed {auto_passed} as safe")
        if blocked:
            handled.append(f"blocked {blocked}")

        tail = ""
        if surfaced:
            n = surfaced
            noun = "decision" if n == 1 else "decisions"
            verb = "is" if n == 1 else "are"
            tail = f"{n} {noun} {verb} waiting for you"

        if handled and tail:
            return "I " + _join_spoken(handled) + f", and {tail}."
        if handled:
            return "I " + _join_spoken(handled) + "."
        if tail:
            return tail[0].upper() + tail[1:] + "."
        return "No decisions to report."

    def status_digest(
        self,
        *,
        raised: int,
        auto_passed: int,
        auto_blocked: int,
        you_approved: int,
        you_rejected: int,
        waiting: int,
        sessions: int | None,
        first_check: bool,
    ) -> str:
        """Spoken "while you were away" status: what Crew asked, what I handled for
        you, what you decided, and what is still waiting (asked last, as a question,
        so the voice session stays open for the answer)."""
        since = "since I started watching" if first_check else "since you last checked"
        out: list[str] = []
        if raised:
            noun = "approval" if raised == 1 else "approvals"
            out.append(f"{since[0].upper()}{since[1:]}, Crew asked for {raised} {noun}.")
            handled = []
            if auto_passed:
                handled.append(f"passed {auto_passed} as safe")
            if auto_blocked:
                ones = "one" if auto_blocked == 1 else "ones"
                handled.append(f"blocked {auto_blocked} dangerous {ones}")
            if handled:
                out.append("I " + _join_spoken(handled) + ".")
        else:
            out.append(f"Nothing new {since}.")
        yours = []
        if you_approved:
            yours.append(f"approved {you_approved}")
        if you_rejected:
            yours.append(f"rejected {you_rejected}")
        if yours:
            out.append("You " + _join_spoken(yours) + ".")
        if sessions is not None:
            out.append(f"Crew has {sessions} active session{'' if sessions == 1 else 's'}.")
        if waiting:
            if waiting == 1:
                out.append("1 decision is waiting for you. Do you want to hear it?")
            else:
                out.append(f"{waiting} decisions are waiting for you. "
                           "Do you want to hear the most important one?")
        return " ".join(out)


# ── helpers ──

# Words in a task's own final message that suggest it hit trouble. Deliberately
# conservative: we only flag when the task itself reports difficulty, and we phrase
# the result as "reported a problem", never assert a definitive failure.
_TROUBLE_WORDS = (
    "failed", "failure", "errored", "exception", "traceback",
    "not found", "cannot", "can't", "could not", "couldn't", "unable",
    "denied", "permission denied", "timed out", "timeout", "crash",
    "non-zero", "abort", "fatal",
    # "error" is handled specially below (skip "no errors"/"0 errors"); a bare
    # "exit status"/"exit code" is NOT a trouble word — only a non-zero one is,
    # matched by the regex in _EXIT_FAILURE.
    "error",
)
# Words that flip a trouble-word into a non-event ("no errors", "without failure",
# "zero failures", "0 errors", "doesn't exist" is intentionally still a trouble via
# "not found"/"cannot" only, not here).
_NEGATION_BEFORE = ("no ", "without", "zero", "0 ")

# A non-zero exit means failure; "exit status 0" / "exit code 0" means success.
_EXIT_FAILURE = re.compile(r"exit (?:status|code)\s*[:=]?\s*(\d+)")


def _looks_troubled(message: str) -> bool:
    if not message:
        return False
    low = message.lower()

    # Explicit exit codes: non-zero => trouble; zero => a success signal, ignore.
    for m in _EXIT_FAILURE.finditer(low):
        if m.group(1) != "0":
            return True

    for word in _TROUBLE_WORDS:
        idx = low.find(word)
        if idx == -1:
            continue
        # Skip if negated just before ("no errors", "without failure", "0 errors").
        prefix = low[max(0, idx - 10):idx]
        if any(neg in prefix for neg in _NEGATION_BEFORE):
            continue
        return True
    return False


def _trouble_reason(message: str) -> str:
    """A short, masked phrase from the task's own message explaining the trouble.

    Prefers the first sentence that itself looks troubled; clipped to a few words
    so the spoken answer stays short. Never echoes the whole log.
    """
    sentences = _split_sentences(message)
    for sentence in sentences:
        if _looks_troubled(sentence):
            return _clip(mask_secrets(sentence.strip(" .:-")), max_words=12)
    # Fall back to the first sentence if the match was only across the whole message.
    if sentences:
        return _clip(mask_secrets(sentences[0].strip(" .:-")), max_words=12)
    return ""


def _split_sentences(text: str) -> list[str]:
    out: list[str] = []
    buf = ""
    for ch in text.replace("\n", " "):
        buf += ch
        if ch in ".!?":
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


def _short_title(title: str, max_words: int = 8) -> str:
    title = title.strip().rstrip("…").strip()
    words = title.split()
    if len(words) <= max_words:
        return title or "a task"
    return " ".join(words[:max_words])


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
