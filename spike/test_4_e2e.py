"""Spike 4: END TO END single flow.
Fire a task -> catch the permission FAST -> approve BEFORE the deny-timeout ->
does the file REALLY get created?  (full proof of the approval mechanism)
"""
import json
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

BASE = "http://localhost:5476"
TOKEN = subprocess.check_output(["kirocrew", "token"], text=True).strip().split("token=", 1)[1]
SLOT = "spike-e2e"
TARGET = Path.home() / ".kiro" / "crew" / "workspace" / "spike_e2e.txt"


def _u(p):
    return f"{BASE}{p}{'&' if '?' in p else '?'}token={TOKEN}"


def get(p):
    req = urllib.request.Request(_u(p), headers={"Origin": BASE})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def post(p, body):
    req = urllib.request.Request(_u(p), data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip() else {}


def fire(p, body):
    req = urllib.request.Request(_u(p), data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Origin": BASE})
    try:
        urllib.request.urlopen(req, timeout=2)
    except (socket.timeout, urllib.error.URLError, TimeoutError):
        pass


def pending_approval():
    slot = get(f"/api/chat/slots/{SLOT}")
    # take the MOST RECENT permission message (not an old one from history)
    for m in reversed(slot.get("messages", [])):
        if m.get("role") == "permission":
            meta = m.get("meta", {})
            aid = meta.get("approval_id") or meta.get("request_id")
            if aid:
                return aid, m.get("content", "")
    return None, None


# cleanup: delete the file and the OLD slot, start fresh
if TARGET.exists():
    TARGET.unlink()
try:
    req = urllib.request.Request(_u(f"/api/chat/slots/{SLOT}"), method="DELETE",
                                 headers={"Origin": BASE})
    urllib.request.urlopen(req, timeout=10)
except Exception:
    pass
time.sleep(1)
try:
    post("/api/chat/slots", {"name": SLOT})
except Exception:
    pass

print("=== fire the task ===")
fire("/api/chat", {"slot": SLOT,
                   "message": "Create a file named spike_e2e.txt containing exactly: WORKS. Use file tools."})

print("=== catch the permission FAST (1s interval) ===")
aid = None
for i in range(40):
    time.sleep(1)
    aid, tool = pending_approval()
    if aid:
        print(f"[{i}s] CAUGHT: {tool}  aid={aid}")
        break
    if i % 5 == 0:
        print(f"[{i}s] no approval yet...")

if not aid:
    print("!! could not catch an approval"); raise SystemExit(1)

print("=== approve IMMEDIATELY ===")
r = post(f"/api/chat/slots/{SLOT}/approve", {"action": "approved", "request_id": aid})
print("approve:", r)

print("=== does the file appear? (watch 10s) ===")
for i in range(10):
    time.sleep(1)
    if TARGET.exists():
        print(f"[{i}s] FILE CREATED! content: {TARGET.read_text()!r}")
        break
else:
    print("file still missing")

print("\n=== LAST ASSISTANT MESSAGE ===")
slot = get(f"/api/chat/slots/{SLOT}")
for m in reversed(slot.get("messages", [])):
    if m.get("role") == "assistant":
        print(str(m.get("content"))[:200]); break
