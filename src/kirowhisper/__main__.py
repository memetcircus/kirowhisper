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
        # SSE mode (json_response=False, the default): elicitation is a server->client
        # request that needs the back-channel the SSE stream provides. json_response
        # has no back-channel, so ctx.elicit() raises NoBackChannelError. The tradeoff
        # is that tunnels drop idle SSE streams; we keep the stream alive during an
        # elicitation by pinging the client every ~15s (see triage_next_decision).
        await server.run_streamable_http_async()
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
