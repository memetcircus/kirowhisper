"""Spike 3b: read the pending permission (approval_id) from slot messages and
APPROVE via /api/chat/slots/{slot}/approve. Then check the file was really created.
"""
import json
import subprocess
import time
import urllib.request
from pathlib import Path

BASE = "http://localhost:5476"
TOKEN = subprocess.check_output(["kirocrew", "token"], text=True).strip().split("token=", 1)[1]
SLOT = "spike-approval-test"


def _u(path):
    sep = "&" if "?" in path else "?"
    return f"{BASE}{path}{sep}token={TOKEN}"


def get(path):
    req = urllib.request.Request(_u(path), headers={"Origin": BASE})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def post(path, body):
    req = urllib.request.Request(_u(path), data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip() else {}


def find_pending_approval():
    slot = get(f"/api/chat/slots/{SLOT}")
    for m in slot.get("messages", []):
        if m.get("role") == "permission":
            meta = m.get("meta", {})
            aid = meta.get("approval_id") or meta.get("request_id")
            if aid:
                return aid, m.get("content", ""), meta
    return None, None, None


print("=== find the pending approval ===")
aid, content, meta = find_pending_approval()
print("approval_id:", aid)
print("tool:", content)
print("purpose/input:", str(meta.get("tool_input"))[:120] if meta else None,
      "| read_only:", meta.get("is_read_only") if meta else None,
      "| shell:", meta.get("is_shell") if meta else None)

if not aid:
    print("!! no pending approval (maybe it timed out and was denied). Stopping.")
    raise SystemExit(0)

print("\n=== send APPROVE (action=approved, request_id=approval_id) ===")
try:
    r = post(f"/api/chat/slots/{SLOT}/approve", {"action": "approved", "request_id": aid})
    print("approve response:", str(r)[:250])
except Exception as e:
    print("approve ERROR:", repr(e)[:300])

print("\n=== wait 8s, was the file really created? ===")
time.sleep(8)
f = Path.home() / ".kiro" / "crew" / "workspace" / "spike_hello.txt"
print("file exists:", f.exists())
if f.exists():
    print("content:", repr(f.read_text()))

slot = get(f"/api/chat/slots/{SLOT}")
print("running:", slot.get("running"))
# last tool/assistant message
for m in reversed(slot.get("messages", [])):
    if m.get("role") in ("assistant", "tool"):
        print("last message:", m.get("role"), "->", str(m.get("content"))[:150])
        break
