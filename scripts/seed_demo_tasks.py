"""Seed the local Kiro Crew with several live demo tasks at once, so KiroWhisper
has a realistic mix of pending approvals to triage by voice.

The point of the demo: many decisions pile up, but Ambient Awareness only makes
noise about the risky ones. We create separate chat slots, each asking Crew to
perform ONE tool action of a known risk, so they surface as parallel approvals:

    LOW  -> create a text file            (safe, reversible)
    LOW  -> create another text file      (safe, reversible)
    HIGH -> delete a file                 (destructive)
    HIGH -> run `rm -rf` in a shell       (destructive shell)
    HIGH -> read a credentials/.env file  (secret exposure)

In interactive approval mode Crew pauses at each tool call and raises an approval
instead of executing it, so nothing destructive actually runs.

Usage:
    python scripts/seed_demo_tasks.py            # seed the default mix
    python scripts/seed_demo_tasks.py --status   # just show current pending
"""

from __future__ import annotations

import asyncio
import sys
import time

from kirowhisper.config import load_config
from kirowhisper.gateway_client import GatewayClient

# (label, task text). One tool action each so each becomes a single approval.
DEMO_TASKS: list[tuple[str, str]] = [
    ("low-create-1",
     "Use your file-write tool to create a file named notes_a.txt containing the text 'hello a'. Do only this one step."),
    ("low-create-2",
     "Use your file-write tool to create a file named notes_b.txt containing the text 'hello b'. Do only this one step."),
    ("high-delete",
     "Use your file tools to delete the file docs/rules.txt. Do only this one step."),
    ("high-shell",
     "Use your shell tool to run exactly: rm -rf build_output. Do only this one step."),
    ("high-secret",
     "Use your file-read tool to read the file .env and show its contents. Do only this one step."),
]


async def show_pending(gw: GatewayClient) -> int:
    pending = await gw.list_pending_approvals()
    print(f"\n=== pending approvals: {len(pending)} ===")
    for ap in pending:
        print(f"  [{ap.slot}] {ap.request_id}")
        print(f"      tool: {ap.tool_title}")
        if ap.purpose:
            print(f"      purpose: {ap.purpose[:80]}")
    return len(pending)


async def main() -> None:
    cfg = load_config()
    async with GatewayClient(cfg.gateway) as gw:
        if "--status" in sys.argv:
            await show_pending(gw)
            return

        stamp = int(time.time())
        created_slots: list[str] = []

        for i, (label, task) in enumerate(DEMO_TASKS):
            name = f"kw-{label}-{stamp}"
            await gw.create_slot(name)
            # discover the real slot key
            slots = await gw.list_slots()
            slot = next((s for s in slots if name in s), slots[-1])
            created_slots.append(slot)
            print(f"[{i+1}/{len(DEMO_TASKS)}] {label} -> slot {slot}")
            await gw.send_message(slot, task)
            await asyncio.sleep(1.0)  # small stagger so Crew accepts each cleanly

        print("\nAll tasks sent. Waiting for approvals to surface...")
        for i in range(12):
            await asyncio.sleep(4)
            n = await show_pending(gw)
            if n >= 3:
                print("\nEnough approvals are pending for the demo.")
                break

        print("\nSlots created this run:")
        for s in created_slots:
            print("   ", s)


if __name__ == "__main__":
    asyncio.run(main())
