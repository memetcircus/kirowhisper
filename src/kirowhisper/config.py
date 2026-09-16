"""Central configuration for KiroWhisper.

All values can be overridden via environment variables so nothing is hard-coded
and no secrets live in source. Defaults match the local Kiro Crew Gateway and
the AWS region verified during the spike.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class GatewayConfig:
    """Kiro Crew Gateway connection settings.

    Auth verified in spike: requests carry ``?token=<JWT>`` (from ``kirocrew
    token``) AND an ``Origin`` header equal to ``base_url`` — the Gateway's
    ``deny_non_dashboard_caller`` refuses requests without it.
    """

    base_url: str = field(
        default_factory=lambda: _env("KIROWHISPER_GATEWAY_URL", "http://localhost:5476")
    )
    # Command whose stdout contains "...token=<JWT>"; used to fetch a fresh token.
    token_command: str = field(
        default_factory=lambda: _env("KIROWHISPER_TOKEN_CMD", "kirocrew token")
    )
    # Optional explicit token (overrides token_command when set). Never commit this.
    token: str = field(
        default_factory=lambda: _env("KIROWHISPER_GATEWAY_TOKEN", "")
    )
    request_timeout_s: float = field(
        default_factory=lambda: _env_float("KIROWHISPER_HTTP_TIMEOUT", 15.0)
    )

    @property
    def origin(self) -> str:
        """Origin header value the Gateway requires (must equal base_url)."""
        return self.base_url.rstrip("/")


@dataclass(frozen=True)
class BedrockConfig:
    """Amazon Bedrock settings for risk classification and summarization.

    Region us-east-1 verified during setup (Nova models + credits live there).
    """

    region: str = field(default_factory=lambda: _env("AWS_REGION", "us-east-1"))
    # Fast/cheap model for the common path (risk classify + short summaries).
    fast_model_id: str = field(
        default_factory=lambda: _env(
            "KIROWHISPER_BEDROCK_FAST_MODEL", "amazon.nova-lite-v1:0"
        )
    )
    # Optional stronger model for nuanced risk calls when the fast one is unsure.
    strong_model_id: str = field(
        default_factory=lambda: _env("KIROWHISPER_BEDROCK_STRONG_MODEL", "")
    )


@dataclass(frozen=True)
class AmbientConfig:
    """Ambient Awareness engine tuning."""

    # Poll interval for pending approvals. Deny-on-silence is ~60-75s, so a few
    # seconds leaves ample margin (design decision).
    poll_interval_s: float = field(
        default_factory=lambda: _env_float("KIROWHISPER_POLL_INTERVAL", 3.0)
    )
    # Retry backoff cap when the Gateway is unreachable.
    max_backoff_s: float = field(
        default_factory=lambda: _env_float("KIROWHISPER_MAX_BACKOFF", 30.0)
    )


@dataclass(frozen=True)
class Config:
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    bedrock: BedrockConfig = field(default_factory=BedrockConfig)
    ambient: AmbientConfig = field(default_factory=AmbientConfig)


def load_config() -> Config:
    """Build configuration from defaults + environment overrides."""
    return Config()
