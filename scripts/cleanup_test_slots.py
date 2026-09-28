"""Developer-only cleanup for the throwaway chat slots our test/demo scripts create.

DESIGN NOTE — why this lives in scripts/, not in GatewayClient or an MCP tool:
deleting a chat slot is destructive and irreversible. It discards the slot's whole
conversation history and any task context, so it must never be reachable from the
voice/MCP surface, where a single misheard word could wipe real work. That directly
contradicts KiroWhisper's whole promise (protect the risky, fail safe). Slot deletion
is therefore intentionally kept out of the product and available only here, as an
explicit developer tool.

Safety guards:
  - Only slots whose name starts with a known TEST_PREFIX are deleted, so a real
    user's slots are never touched, even by accident.
  - --dry-run lists what *would* be deleted without deleting anything.
  - Expiring an approval (deny-on-silence) is not the same as deleting its slot: the
    approval is already safely resolved, but the slot still holds its history. We only
    delete slots we ourselves created for testing.

Usage:
    python scripts/cleanup_test_slots.py --dry-run   # show what would go
    python scripts/cleanup_test_slots.py             # delete the test slots
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

import httpx

from kirowhisper.config import load_config

# Only slots with one of these name prefixes are ever eligible for deletion.
TEST_PREFIXES = ("kw-simdemo-", "kw-livedemo-", "kw-safety-smoke-", "kw-simulator-live-",
                 "kw-sim-now-", "kw-demo-loop-", "kw-multi-", "kw-structtest", "kw-safety-",
                 "kw-high-", "kw-lowread-", "kw-approvetest-")


def _token(cmd: str) -> str:
    out = subprocess.check_output(cmd.split(), text=True, timeout=15).strip()
    return out.split("token=", 1)[1].strip() if "token=" in out else out


async def _list_slots(client: httpx.AsyncClient, base: str, params, headers) -> list[str]:
    resp = await client.get(f"{base}/api/chat/slots", params=params, headers=headers)
    raw = resp.json()
    entries = raw if isinstance(raw, list) else raw.get("slots", [])
    keys: list[str] = []
    for s in entries:
        key = (s.get("key") or s.get("name")) if isinstance(s, dict) else s
        if key:
            keys.append(str(key))
    return keys


async def main() -> None:
    dry_run = "--dry-run" in sys.argv
    cfg = load_config().gateway
    base = cfg.base_url.rstrip("/")
    params = {"token": _token(cfg.token_command)}
    headers = {"Origin": cfg.origin}

    async with httpx.AsyncClient(timeout=15) as client:
        slots = await _list_slots(client, base, params, headers)
        targets = [s for s in slots if s.startswith(TEST_PREFIXES)]
        skipped = [s for s in slots if s not in targets]

        print(f"{len(slots)} slot(s) total; {len(targets)} match a test prefix.")
        for s in skipped:
            print(f"  keep (not a test slot): {s}")
        for s in targets:
            if dry_run:
                print(f"  would delete: {s}")
                continue
            resp = await client.request(
                "DELETE", f"{base}/api/chat/slots/{s}", params=params, headers=headers
            )
            print(f"  deleted {s} -> {resp.status_code}")

        if not dry_run:
            left = await _list_slots(client, base, params, headers)
            print(f"remaining slots: {len(left)}")


if __name__ == "__main__":
    asyncio.run(main())
