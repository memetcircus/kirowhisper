"""Pretty-print KiroWhisper's live MCP tool surface for the demo closing shot.

Queries the running MCP server over Streamable HTTP (the same endpoint Alexa+
calls) and prints the real tools/list result, grouped the way a user meets them.
Nothing is hard-coded — if a tool is added or removed, this reflects it.

Usage:
    python scripts/show_mcp_tools.py                      # local server
    MCP_URL=https://<tunnel>/mcp python scripts/show_mcp_tools.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp")

# One-line purpose per tool, grouped by what the user is doing.
GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Discover", [
        ("help", "spoken \"what can you do\" menu, for eyes-free use"),
    ]),
    ("Check in", [
        ("get_status", "while-you-were-away digest"),
        ("check_task_health", "which task failed / how tasks are doing"),
        ("describe_session", "what a session is working on"),
    ]),
    ("Decide", [
        ("get_pending_decisions", "read the highest-risk decision aloud"),
        ("explain_top", "why that decision is risky"),
        ("approve_top", "approve it (two-step confirm)"),
        ("reject_top", "reject it"),
        ("approve_all_safe", "clear the rule-certain safe backlog"),
        ("trust_session", "trust a session going forward"),
        ("approve", "approve a specific request by id"),
        ("reject", "reject a specific request by id"),
    ]),
    ("Summarize", [
        ("summarize", "a task result or diff, voice-friendly"),
    ]),
]

GREEN = "\033[32m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
RESET = "\033[0m"


def fetch_tool_names(url: str) -> list[str]:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode()
    # Streamable HTTP may return an SSE frame ("data: {json}") or plain JSON.
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[len("data:"):].strip()
        if not line.startswith("{"):
            continue
        obj = json.loads(line)
        tools = obj.get("result", {}).get("tools")
        if tools is not None:
            return [t["name"] for t in tools]
    raise SystemExit("Could not parse tools/list response")


def main() -> None:
    names = set(fetch_tool_names(MCP_URL))
    total = len(names)

    print()
    print(f"  {BOLD}KiroWhisper — MCP server{RESET}")
    print(f"  {DIM}MCP spec 2025-11-25  ·  Streamable HTTP  ·  {total} tools{RESET}")
    print()

    shown = 0
    for group, tools in GROUPS:
        print(f"  {CYAN}{group}{RESET}")
        for name, desc in tools:
            mark = f"{GREEN}●{RESET}" if name in names else " "
            print(f"    {mark} {BOLD}{name:<22}{RESET}{DIM}{desc}{RESET}")
            if name in names:
                shown += 1
        print()

    if shown != total:
        print(f"  {DIM}(server also exposes {total - shown} tool(s) not listed here){RESET}")
        print()


if __name__ == "__main__":
    sys.exit(main())
