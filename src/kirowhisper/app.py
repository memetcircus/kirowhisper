"""Application wiring — build the full KiroWhisper stack from config.

Creates the Gateway client, risk classifier (rules + Bedrock), summarizer, audit
log, and Ambient Awareness engine, then bundles them for the MCP server.
"""

from __future__ import annotations

from .ambient import AmbientEngine
from .audit import AuditLog
from .bedrock import BedrockClassifier
from .config import Config, load_config
from .gateway_client import GatewayClient
from .mcp_server import KiroWhisperServices, build_server
from .risk import RiskClassifier
from .summarizer import Summarizer


def build_services(
    config: Config | None = None, *, use_bedrock: bool = True
) -> KiroWhisperServices:
    """Construct the full service bundle. Bedrock is optional (deterministic fallback)."""
    cfg = config or load_config()

    gateway = GatewayClient(cfg.gateway)
    audit = AuditLog()

    if use_bedrock:
        bedrock = BedrockClassifier(cfg.bedrock)
        classifier = RiskClassifier(model_classify=bedrock.as_model_classify())
        # Summarizer shares a bedrock-runtime client lazily; pass None to keep it
        # on the deterministic fallback unless a client is wired explicitly.
        summarizer = Summarizer(cfg.bedrock, bedrock_client=None)
    else:
        classifier = RiskClassifier()  # rules only; inconclusive -> UNKNOWN (safe)
        summarizer = Summarizer(cfg.bedrock)

    ambient = AmbientEngine(gateway, classifier, audit, cfg.ambient)

    return KiroWhisperServices(
        gateway=gateway,
        ambient=ambient,
        summarizer=summarizer,
        audit=audit,
        config=cfg,
    )


def build_app(config: Config | None = None, *, use_bedrock: bool = True):
    """Build the MCP server ready to run over Streamable HTTP."""
    services = build_services(config, use_bedrock=use_bedrock)
    return build_server(services), services
