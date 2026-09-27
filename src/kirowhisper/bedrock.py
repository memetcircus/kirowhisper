"""Amazon Bedrock layer — nuanced risk classification and voice summaries.

Used by the risk classifier only when the deterministic rules are inconclusive,
and by the summarizer to turn raw data into voice-friendly text. Isolating boto3
here keeps risk.py testable without AWS.

Fail-safe (NFR-1): any Bedrock error, timeout, or unparseable output yields an
UNKNOWN risk — never a LOW. The engine then surfaces the request to a human.
"""

from __future__ import annotations

import json

from .config import BedrockConfig
from .models import Approval, RiskAssessment, RiskLevel

_CLASSIFY_SYSTEM = (
    "You are a security classifier for an autonomous coding agent's tool calls. "
    "Given a pending operation, decide its risk to the user's system and data. "
    "Reply with STRICT JSON only: "
    '{"level":"low|high|unknown","reason":"<=15 words","spoken":"<=20 words, voice-friendly"}. '
    "Use 'high' for anything destructive, irreversible, shell execution, secret "
    "exposure, or production impact. Use 'low' only for clearly reversible, "
    "read-only, or trivial edits. If you are not sure, use 'unknown'. Never guess 'low'."
)


class BedrockClassifier:
    """Calls a Bedrock model to classify an approval. Lazy-imports boto3."""

    def __init__(self, config: BedrockConfig, *, client=None) -> None:
        self._cfg = config
        self._client = client  # inject for tests; else created lazily

    def _get_client(self):
        if self._client is None:
            import boto3  # lazy: only needed at runtime, not for unit tests

            session = (
                boto3.Session(profile_name=self._cfg.profile)
                if self._cfg.profile
                else boto3.Session()
            )
            self._client = session.client("bedrock-runtime", region_name=self._cfg.region)
        return self._client

    def classify(self, approval: Approval) -> RiskAssessment:
        prompt = (
            f"Tool: {approval.tool_title}\n"
            f"Purpose: {approval.purpose}\n"
            f"Input/diff:\n{approval.diff[:4000]}\n"
            f"is_read_only={approval.is_read_only} is_shell={approval.is_shell}"
        )
        try:
            raw = self._invoke(prompt)
        except Exception as exc:  # noqa: BLE001 - any failure is fail-safe
            return RiskAssessment(RiskLevel.UNKNOWN, f"bedrock error: {exc!r}"[:180])
        return self._parse(raw)

    def _invoke(self, prompt: str) -> str:
        """Invoke via the Bedrock Converse API (model-agnostic across Nova/Claude)."""
        client = self._get_client()
        resp = client.converse(
            modelId=self._cfg.fast_model_id,
            system=[{"text": _CLASSIFY_SYSTEM}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 200, "temperature": 0.0},
        )
        return resp["output"]["message"]["content"][0]["text"]

    @staticmethod
    def _parse(raw: str) -> RiskAssessment:
        text = raw.strip()
        # Extract the first JSON object if the model added prose around it.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
        try:
            data = json.loads(text)
        except ValueError:
            return RiskAssessment(RiskLevel.UNKNOWN, "unparseable model output")
        level_str = str(data.get("level", "")).strip().lower()
        try:
            level = RiskLevel(level_str)
        except ValueError:
            return RiskAssessment(RiskLevel.UNKNOWN, f"unknown level: {level_str!r}")
        return RiskAssessment(
            level=level,
            reason=str(data.get("reason", ""))[:200],
            spoken_summary=str(data.get("spoken", ""))[:240],
        )

    def as_model_classify(self):
        """Return a callable suitable for RiskClassifier(model_classify=...)."""
        return self.classify

    @property
    def runtime_client(self):
        """The underlying bedrock-runtime client (created lazily). Shareable."""
        return self._get_client()
