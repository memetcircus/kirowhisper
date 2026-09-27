"""Entry points for KiroWhisper.

    kirowhisper            # MCP server (Streamable HTTP) — for Alexa+/MCP clients
    kirowhisper voice      # voice simulation web app + Ambient engine — for the demo

The Ambient Awareness engine starts alongside either server so approvals are
watched as soon as it comes up.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys

from .app import build_app, build_voice_app


async def _run_mcp() -> None:
    server, services = build_app()
    services.ambient.start()
    try:
        # Stateless HTTP: every request stands alone, so there is no server-side
        # session to expire and no "Session not found" after an idle gap. The
        # voice flow (get_pending_decisions + approve_top/reject_top) makes no
        # server->client requests, so it needs neither an SSE back-channel nor a
        # persistent session. Earlier we ran SSE for ctx.elicit(), but the Alexa
        # bridge keeps one long-lived agent per user and cloudflared drops idle
        # SSE streams, so that session died between turns and the next tool call
        # failed. Elicitation is gone; stateless removes the whole failure class.
        await server.run_streamable_http_async(stateless_http=True, json_response=True)
    finally:
        await services.ambient.stop()
        with contextlib.suppress(Exception):
            await services.gateway.aclose()


async def _run_voice(host: str = "127.0.0.1", port: int = 8800) -> None:
    import uvicorn

    app, services = build_voice_app()
    services.ambient.start()
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        await services.ambient.stop()
        with contextlib.suppress(Exception):
            await services.gateway.aclose()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "mcp"
    if mode == "voice":
        asyncio.run(_run_voice())
    else:
        asyncio.run(_run_mcp())


if __name__ == "__main__":
    main()
