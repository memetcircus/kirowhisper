"""Unit tests for the Summarizer (fallback path + Bedrock path + safety)."""

from __future__ import annotations

from kirowhisper.config import BedrockConfig
from kirowhisper.models import Approval, RiskAssessment, RiskLevel
from kirowhisper.summarizer import Summarizer


def _ap(title="", diff="", ro=False, sh=False) -> Approval:
    return Approval(request_id="x", slot="s", tool_title=title, diff=diff,
                    is_read_only=ro, is_shell=sh)


def test_prefers_risk_spoken_summary():
    s = Summarizer(BedrockConfig())  # no client
    risk = RiskAssessment(RiskLevel.HIGH, "x", "drops the users table")
    out = s.approval_summary(_ap("edit"), risk)
    assert out == "drops the users table"


def test_fallback_high_flags_danger():
    s = Summarizer(BedrockConfig())
    out = s.approval_summary(_ap("Delete auth.js", "-a\n-b\n+c"),
                             RiskAssessment(RiskLevel.HIGH, "irreversible delete"))
    assert "Careful" in out
    assert "irreversible" in out.lower()


def test_fallback_low_is_reassuring():
    s = Summarizer(BedrockConfig())
    out = s.approval_summary(_ap("Read file"), RiskAssessment(RiskLevel.LOW, "read only"))
    assert "low risk" in out.lower()


def test_fallback_unknown_asks_the_user():
    s = Summarizer(BedrockConfig())
    out = s.approval_summary(_ap("Edit", "+a\n+b"), RiskAssessment(RiskLevel.UNKNOWN, ""))
    assert "asking you" in out.lower() or "not sure" in out.lower()


def test_summary_masks_secrets():
    s = Summarizer(BedrockConfig())
    risk = RiskAssessment(RiskLevel.HIGH, "x", "writes api_key=supersecret123 to log")
    out = s.approval_summary(_ap("edit"), risk)
    assert "supersecret123" not in out
    assert "***REDACTED***" in out


def test_summary_is_clipped():
    s = Summarizer(BedrockConfig())
    long_spoken = " ".join(["word"] * 100)
    out = s.approval_summary(_ap("edit"), RiskAssessment(RiskLevel.LOW, "", long_spoken))
    assert len(out.split()) <= 29  # clipped near max_words


def test_bedrock_path_used_when_client_present():
    class Fake:
        def converse(self, **_):
            text = "It deletes the old login, 42 lines, irreversible."
            return {"output": {"message": {"content": [{"text": text}]}}}

    s = Summarizer(BedrockConfig(), bedrock_client=Fake())
    out = s.approval_summary(_ap("Delete", "-x"), RiskAssessment(RiskLevel.HIGH, "delete"))
    assert "deletes the old login" in out


def test_bedrock_error_falls_back():
    class Boom:
        def converse(self, **_):
            raise RuntimeError("network")

    s = Summarizer(BedrockConfig(), bedrock_client=Boom())
    out = s.approval_summary(_ap("Delete auth.js", "-x"), RiskAssessment(RiskLevel.HIGH, "delete"))
    # Falls back to deterministic phrasing, still non-empty and safe.
    assert out
    assert "Careful" in out


def test_status_summary_phrasing():
    s = Summarizer(BedrockConfig())
    assert s.status_summary(done=2, pending=1) == "2 tasks done and 1 waiting for you."
    assert s.status_summary(done=1, pending=0) == "1 task done."
    assert s.status_summary(done=0, pending=0) == "Nothing running right now."
    assert "3 failed" in s.status_summary(done=1, pending=1, failed=3)


def test_ambient_summary_phrasing():
    s = Summarizer(BedrockConfig())
    out = s.ambient_summary(auto_passed=19, blocked=3, surfaced=1)
    assert out == "I passed 19 as safe and blocked 3, and 1 decision is waiting for you."
    only3 = s.ambient_summary(auto_passed=0, blocked=0, surfaced=3)
    assert only3 == "3 decisions are waiting for you."
    assert s.ambient_summary(auto_passed=0, blocked=0, surfaced=0) == "No decisions to report."
