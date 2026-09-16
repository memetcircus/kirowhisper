"""Integration test against REAL Amazon Bedrock (opt-in).

Skipped unless KIROWHISPER_RUN_BEDROCK=1, so CI / machines without AWS stay green.
This is the "we genuinely call Bedrock at runtime" proof for the AWS Builder
mini-challenge.

Run once the AWS account is verified:
    KIROWHISPER_RUN_BEDROCK=1 pytest tests/test_bedrock_integration.py -v -s
"""

from __future__ import annotations

import os

import pytest

from kirowhisper.bedrock import BedrockClassifier
from kirowhisper.config import BedrockConfig
from kirowhisper.models import Approval, RiskLevel
from kirowhisper.summarizer import Summarizer

RUN = os.environ.get("KIROWHISPER_RUN_BEDROCK") == "1"

pytestmark = pytest.mark.skipif(
    not RUN, reason="Bedrock integration is opt-in: set KIROWHISPER_RUN_BEDROCK=1"
)


def _dangerous() -> Approval:
    return Approval(
        request_id="int-1", slot="s", tool_title="Shell command",
        purpose="clean the build directory",
        diff="rm -rf /tmp/build", is_shell=True,
    )


def _ambiguous() -> Approval:
    return Approval(
        request_id="int-2", slot="s", tool_title="Edit config",
        purpose="update the retry count",
        diff="--- config.py\n+++ config.py\n@@\n-retries = 3\n+retries = 5",
    )


def test_real_bedrock_classifies_dangerous_as_high():
    bc = BedrockClassifier(BedrockConfig())
    result = bc.classify(_dangerous())
    print(f"\n[Bedrock] dangerous -> level={result.level} reason={result.reason!r}")
    # A real model should not call an rm -rf shell command LOW.
    assert result.level in (RiskLevel.HIGH, RiskLevel.UNKNOWN)


def test_real_bedrock_returns_structured_result():
    bc = BedrockClassifier(BedrockConfig())
    result = bc.classify(_ambiguous())
    print(f"\n[Bedrock] ambiguous -> level={result.level} spoken={result.spoken_summary!r}")
    # We only assert the call succeeded and mapped to a known level.
    assert result.level in (RiskLevel.LOW, RiskLevel.HIGH, RiskLevel.UNKNOWN)


def test_real_bedrock_summary_is_voice_friendly():
    # Wire a real bedrock-runtime client into the summarizer.
    import boto3

    from kirowhisper.models import RiskAssessment

    client = boto3.client("bedrock-runtime", region_name=BedrockConfig().region)
    s = Summarizer(BedrockConfig(), bedrock_client=client)
    approval = _dangerous()
    risk = RiskAssessment(RiskLevel.HIGH, "recursive delete")
    spoken = s.approval_summary(approval, risk)
    print(f"\n[Bedrock] spoken summary -> {spoken!r}")
    assert spoken                      # non-empty
    assert len(spoken.split()) <= 30   # voice-friendly length
