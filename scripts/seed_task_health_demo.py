"""Seed a realistic task-health mix for a live 'which task failed?' demo.

Creates two sessions and drives each to completion so a health check has real
data to report:
  - one task whose shell command FAILS (command not found) -> "reported a problem"
  - one task that SUCCEEDS (echo) -> "finished cleanly"

Any pending shell pre-approval is auto-approved here so the command actually runs
and produces its real outcome. Nothing destructive is run (bad command + echo).

Usage:
    python scripts/seed_task_health_demo.py
"""

from __future__ import annotations

import asyncio
import time

from kirowhisper.config import load_config
from kirowhisper.gateway_client import GatewayClient


async def seed(gw: GatewayClient, label: str, task: str) -> str:
    name = f"kw-status-health-{label}-{int(time.time())}"
    await gw.create_slot(name)
    slots = await gw.list_slots()
    slot = next((s for s in slots if name in s), slots[-1])
    await gw.send_message(slot, task)
    return slot


async def drive_to_done(gw: GatewayClient, slot: str, rounds: int = 20) -> None:
    for _ in range(rounds):
        await asyncio.sleep(3)
        ap = await gw.get_slot_pending_approval(slot)
        if ap is not None:
            await gw.approve(ap.slot, ap.request_id)
            continue
        obj = await gw.get_slot(slot)
        if obj.get("running") is False and obj.get("messages"):
            return


async def main() -> None:
    cfg = load_config()
    async with GatewayClient(cfg.gateway) as gw:
        fail_slot = await seed(
            gw, "fail",
            "Use your shell tool to run exactly: this_cmd_does_not_exist_xyz. "
            "Report what happened.",
        )
        ok_slot = await seed(
            gw, "ok",
            "Use your shell tool to run exactly: echo hello-kirowhisper. Report the output.",
        )
        print(f"seeded fail={fail_slot} ok={ok_slot}; driving to completion...")
        await drive_to_done(gw, fail_slot)
        await drive_to_done(gw, ok_slot)

        print("\nDone. Now ask in the Alexa simulator:")
        print('  "open kiro whisper"  ->  "which task failed"')
        print("\nCurrent slot health:")
        for s in await gw.list_slot_summaries():
            print(f"  {s['title'][:45]:45} running={s['running']} "
                  f"last={s['last_message'][:60]!r}")


if __name__ == "__main__":
    asyncio.run(main())
