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


def test_explain_high_says_why_and_reject_outcome():
    s = Summarizer(BedrockConfig())
    ap = Approval(request_id="x", slot="s", tool_title="Delete auth.js",
                  purpose="remove the old login module")
    risk = RiskAssessment(RiskLevel.HIGH, "recursive file removal", deterministic=True)
    out = s.explain(ap, risk)
    assert "safety rule flagged this as high risk" in out.lower()
    assert "because of recursive file removal" in out.lower()
    assert "won't run" in out.lower()  # what rejecting does
    assert "may not be reversible" in out.lower()


def test_explain_low_reassures_and_marks_reversible():
    s = Summarizer(BedrockConfig())
    ap = Approval(request_id="x", slot="s", tool_title="Read config")
    risk = RiskAssessment(RiskLevel.LOW, "read-only access", deterministic=True)
    out = s.explain(ap, risk)
    assert "low risk" in out.lower()
    assert "it's reversible" in out.lower()


def test_explain_unknown_admits_uncertainty():
    s = Summarizer(BedrockConfig())
    ap = Approval(request_id="x", slot="s", tool_title="Run script")
    risk = RiskAssessment(RiskLevel.UNKNOWN, "")
    out = s.explain(ap, risk)
    assert "not sure" in out.lower()
    assert "asking you" in out.lower()


def test_explain_masks_secrets():
    s = Summarizer(BedrockConfig())
    ap = Approval(request_id="x", slot="s", tool_title="Write env",
                  purpose="set api_key=supersecret123 in the config")
    risk = RiskAssessment(RiskLevel.HIGH, "writes a credential", deterministic=True)
    out = s.explain(ap, risk)
    assert "supersecret123" not in out
    assert "***REDACTED***" in out


def test_task_health_names_the_failed_task_first():
    s = Summarizer(BedrockConfig())
    slots = [
        {"slot": "s1", "title": "Shell Command Test", "running": False,
         "awaiting_approval": False,
         "last_message": "As expected, it failed: Exit status 127, command not found."},
        {"slot": "s2", "title": "Build the parser", "running": True,
         "awaiting_approval": False, "last_message": "Working on it."},
        {"slot": "s3", "title": "Write docs", "running": False,
         "awaiting_approval": False, "last_message": "Done, all three files written."},
    ]
    out = s.task_health(slots)
    assert "reported a problem" in out.lower()
    assert "Shell Command Test" in out
    assert "1 still running" in out
    assert "1 finished cleanly" in out


def test_task_health_none_troubled():
    s = Summarizer(BedrockConfig())
    slots = [
        {"slot": "s1", "title": "T1", "running": False, "awaiting_approval": False,
         "last_message": "All tests passed, no errors."},
        {"slot": "s2", "title": "T2", "running": False, "awaiting_approval": True,
         "last_message": "Ready for your approval."},
    ]
    out = s.task_health(slots)
    assert "nothing has reported a failure" in out.lower()
    assert "1 waiting for your approval" in out
    assert "1 finished cleanly" in out


def test_task_health_negation_is_not_a_failure():
    # "no errors" / "without failure" must NOT be flagged as troubled.
    s = Summarizer(BedrockConfig())
    slots = [{"slot": "s1", "title": "Clean run", "running": False,
              "awaiting_approval": False,
              "last_message": "Finished with no errors and zero failures."}]
    out = s.task_health(slots)
    assert "reported a problem" not in out.lower()
    assert "1 finished cleanly" in out


def test_task_health_masks_secrets_in_reason():
    s = Summarizer(BedrockConfig())
    slots = [{"slot": "s1", "title": "Deploy", "running": False,
              "awaiting_approval": False,
              "last_message": "Error: auth failed using api_key=supersecret123 value."}]
    out = s.task_health(slots)
    assert "supersecret123" not in out
    assert "reported a problem" in out.lower()


def test_task_health_exit_status_zero_is_success_not_failure():
    # A successful command reports "exit status 0" — this must NOT be flagged as a
    # problem, while a non-zero exit must be. Regression for a live false positive.
    s = Summarizer(BedrockConfig())
    ok = [{"slot": "s1", "title": "Echo", "running": False, "awaiting_approval": False,
           "last_message": "Output: hello (exit status 0, no stderr)."}]
    assert "nothing has reported a failure" in s.task_health(ok).lower()

    bad = [{"slot": "s1", "title": "Bad", "running": False, "awaiting_approval": False,
            "last_message": "It ran but returned exit status 2."}]
    assert "reported a problem" in s.task_health(bad).lower()


def test_task_health_no_active_sessions():
    s = Summarizer(BedrockConfig())
    assert "no active sessions" in s.task_health([]).lower()


def test_describe_session_fallback_says_task_and_state():
    s = Summarizer(BedrockConfig())  # no Bedrock client -> deterministic
    sess = {
        "title": "Build the parser", "running": True, "awaiting_approval": False,
        "turns": 3, "task": "Write a JSON parser in parser.py and add tests.",
        "last_message": "Added the tokenizer; writing the grammar next.",
    }
    out = s.describe_session(sess)
    assert "Build the parser" in out
    assert "still working" in out.lower()
    assert "json parser" in out.lower()          # the task, lower-cased mid-sentence
    assert "3 steps" in out


def test_describe_session_awaiting_state():
    s = Summarizer(BedrockConfig())
    sess = {"title": "Deploy", "running": False, "awaiting_approval": True,
            "turns": 1, "task": "Deploy to staging.", "last_message": "Ready to deploy."}
    out = s.describe_session(sess)
    assert "waiting for your approval" in out.lower()


def test_describe_session_masks_secrets():
    s = Summarizer(BedrockConfig())
    sess = {"title": "Configure", "running": False, "awaiting_approval": False,
            "turns": 1, "task": "Set api_key=supersecret123 in config.",
            "last_message": "Wrote the config."}
    out = s.describe_session(sess)
    assert "supersecret123" not in out
    assert "***REDACTED***" in out


def test_describe_session_empty():
    s = Summarizer(BedrockConfig())
    assert "don't have a session" in s.describe_session({}).lower()


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


def test_status_digest_while_you_were_away():
    s = Summarizer(BedrockConfig())
    out = s.status_digest(raised=4, auto_passed=2, auto_blocked=1, you_approved=0,
                          you_rejected=0, waiting=1, sessions=3, first_check=False)
    assert out == (
        "Since you last checked, Crew asked for 4 approvals. "
        "I passed 2 as safe and blocked 1 dangerous one. "
        "Crew has 3 active sessions. "
        "1 decision is waiting for you. Do you want to hear it?"
    )


def test_status_digest_reports_user_decisions_and_first_check():
    s = Summarizer(BedrockConfig())
    out = s.status_digest(raised=0, auto_passed=0, auto_blocked=0, you_approved=1,
                          you_rejected=2, waiting=0, sessions=1, first_check=True)
    assert out == ("Nothing new since I started watching. You approved 1 and rejected 2. "
                   "Crew has 1 active session.")
