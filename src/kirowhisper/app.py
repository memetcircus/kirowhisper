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
        # Share the same bedrock-runtime client with the summarizer so it produces
        # real voice-friendly phrasing (falls back deterministically on any error).
        summarizer = Summarizer(cfg.bedrock, bedrock_client=bedrock.runtime_client)
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


def build_voice_app(config: Config | None = None, *, use_bedrock: bool = True):
    """Build the voice-simulation web app (JSON bridge + UI) and its services."""
    from .voice_sim.bridge import VoiceBridge

    services = build_services(config, use_bedrock=use_bedrock)
    bridge = VoiceBridge(services)
    return bridge.app(), services
