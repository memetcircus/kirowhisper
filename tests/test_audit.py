"""Unit tests for the audit log and secret masking."""

from __future__ import annotations

from pathlib import Path

from kirowhisper.audit import AuditLog, mask_secrets
from kirowhisper.models import DecisionAction, RiskLevel


def test_mask_secrets_key_value():
    assert "***REDACTED***" in mask_secrets("api_key=abcdef123456")
    assert "abcdef123456" not in mask_secrets("api_key=abcdef123456")


def test_mask_secrets_aws_key_id():
    assert "***REDACTED***" in mask_secrets("using AKIA1234567890ABCDEF now")


def test_mask_secrets_leaves_plain_text():
    assert mask_secrets("nothing secret here") == "nothing secret here"


def test_audit_record_and_read(tmp_path: Path):
    log = AuditLog(path=tmp_path / "a.jsonl")
    log.record("r1", RiskLevel.HIGH, DecisionAction.SURFACE, "deletes auth.js")
    log.record("r2", RiskLevel.LOW, DecisionAction.AUTO_APPROVE, "read only")
    entries = log.read_all()
    assert len(entries) == 2
    assert entries[0].approval_id == "r1"
    assert entries[0].risk == RiskLevel.HIGH
    assert entries[0].action == DecisionAction.SURFACE


def test_audit_masks_secret_in_reason(tmp_path: Path):
    log = AuditLog(path=tmp_path / "a.jsonl")
    log.record("r1", RiskLevel.HIGH, DecisionAction.AUTO_BLOCK, "blocked api_key=supersecret123")
    raw = (tmp_path / "a.jsonl").read_text()
    assert "supersecret123" not in raw
    assert "***REDACTED***" in raw


def test_audit_summary_counts(tmp_path: Path):
    log = AuditLog(path=tmp_path / "a.jsonl")
    log.record("r1", RiskLevel.LOW, DecisionAction.AUTO_APPROVE)
    log.record("r2", RiskLevel.LOW, DecisionAction.AUTO_APPROVE)
    log.record("r3", RiskLevel.HIGH, DecisionAction.AUTO_BLOCK)
    log.record("r4", RiskLevel.UNKNOWN, DecisionAction.SURFACE)
    summary = log.summary_since(0)
    assert summary["auto_approve"] == 2
    assert summary["auto_block"] == 1
    assert summary["surface"] == 1


def test_audit_read_skips_malformed_lines(tmp_path: Path):
    p = tmp_path / "a.jsonl"
    p.write_text('{"ts":1.0,"approval_id":"ok","risk":"low","action":"surface"}\n'
                 "this is not json\n"
                 '{"broken":true}\n')
    log = AuditLog(path=p)
    entries = log.read_all()
    assert len(entries) == 1
    assert entries[0].approval_id == "ok"
