"""Keep exactly one fresh HIGH-risk approval waiting for a live Alexa demo.

Crew's deny-on-silence expires an unresolved approval in ~60-75s, which is too
short to open the skill and speak by voice. This helper watches the queue and,
whenever nothing is pending, seeds one more shell-delete approval, so a demo
tester always finds a fresh decision no matter how slowly they talk.

Each approval targets its own throwaway file under a temp dir, so an accidental
approve deletes only that scratch file. Stop with Ctrl-C.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from kirowhisper.config import load_config
from kirowhisper.gateway_client import GatewayClient

SCRATCH_DIR = Path("/tmp/kirowhisper-demo")


async def seed_one(gw: GatewayClient) -> None:
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    target = SCRATCH_DIR / f"delete_me_{stamp}.txt"
    target.write_text("throwaway demo file\n")

    name = f"kw-demo-loop-{stamp}"
    await gw.create_slot(name)
    slots = await gw.list_slots()
    slot = next(s for s in slots if name in s)
    cmd = f"rm -- {target}"
    await gw.send_message(
        slot, f"Use your shell tool to run exactly: {cmd}. Do only this one step."
    )

    # Auto-approve any safe read-only pre-step (e.g. a directory listing) so the
    # HIGH-risk shell approval is the one left waiting for the voice user.
    for _ in range(40):
        await asyncio.sleep(2)
        pend = [p for p in await gw.list_pending_approvals() if p.slot == slot]
        if not pend:
            continue
        if pend[0].is_shell:
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] fresh HIGH-risk approval ready: {pend[0].request_id}")
            return
        await gw.approve(pend[0].slot, pend[0].request_id)  # advance the safe pre-step
    print("warning: high-risk approval did not surface for", slot)


async def main() -> None:
    async with GatewayClient(load_config().gateway) as gw:
        print("keeping one fresh approval waiting; Ctrl-C to stop")
        while True:
            pending = await gw.list_pending_approvals()
            if not pending:
                await seed_one(gw)
            await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nstopped")
