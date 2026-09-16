"""Entry point: run the KiroWhisper MCP server over Streamable HTTP.

    kirowhisper           # runs the MCP server (Streamable HTTP)
    python -m kirowhisper

The Ambient Awareness engine starts alongside the server so approvals are watched
as soon as it comes up.
"""

from __future__ import annotations

import asyncio
import contextlib

from .app import build_app


def main() -> None:
    server, services = build_app()

    async def _serve() -> None:
        services.ambient.start()
        try:
            await server.run_streamable_http_async()
        finally:
            await services.ambient.stop()
            with contextlib.suppress(Exception):
                await services.gateway.aclose()

    asyncio.run(_serve())


if __name__ == "__main__":
    main()
