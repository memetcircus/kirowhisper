"""Spike step 3 (APPROVAL - the project's heart):
Start a tool-requiring task in a chat slot -> read pending approval ->
resolve via POST /api/chat/slots/{slot}/approve -> see it continue.

Auth: query ?token=  (from kirocrew token)
Origin header is REQUIRED for dashboard-only endpoints.
"""
import json
import subprocess
import time
import urllib.request

BASE = "http://localhost:5476"
TOKEN = subprocess.check_output(["kirocrew", "token"], text=True).strip().split("token=", 1)[1]
HEADERS = {"Content-Type": "application/json", "Origin": BASE}


def _u(path):
    sep = "&" if "?" in path else "?"
    return f"{BASE}{path}{sep}token={TOKEN}"


def get(path):
    req = urllib.request.Request(_u(path), headers={"Origin": BASE})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def post(path, body, timeout=30):
    req = urllib.request.Request(_u(path), data=json.dumps(body).encode(),
                                 method="POST", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip() else {}


def fire(path, body):
    """Fire a POST without waiting for the response (for long-lived requests like chat)."""
    import socket
    req = urllib.request.Request(_u(path), data=json.dumps(body).encode(),
                                 method="POST", headers=HEADERS)
    try:
        urllib.request.urlopen(req, timeout=3)
    except (socket.timeout, urllib.error.URLError, TimeoutError):
        pass  # we don't wait for the response; the agent keeps working in the background


SLOT = "spike-approval-test"

print("=== 1) create slot ===")
try:
    s = post("/api/chat/slots", {"name": SLOT})
    print("slot:", s.get("key"))
except Exception as e:
    print("slot may already exist:", repr(e)[:120])

print("\n=== 2) send a tool-requiring task ===")
# Writing a file / running a command triggers a tool approval
fire("/api/chat", {"slot": SLOT,
                   "message": "Create a file named spike_hello.txt containing the text HELLO. Use your file tools."})
print("message fired (response not awaited), waiting for the tool approval...")

print("\n=== 3) poll for a pending approval ===")
approved = False
for i in range(20):
    time.sleep(4)
    slot = get(f"/api/chat/slots/{SLOT}")
    pending = slot.get("pending_approval")
    info = slot.get("pending_approval_info")
    running = slot.get("running")
    print(f"[{i*4:>3}s] running={running} pending_approval={pending} "
          f"info={str(info)[:160] if info else None}")
    if pending and info:
        req_id = info.get("request_id") or info.get("id") or ""
        tool = info.get("tool") or info.get("title") or "?"
        print(f"\n  >>> APPROVAL PENDING: tool={tool} request_id={req_id}")
        print("  >>> sending approve...")
        try:
            r = post(f"/api/chat/slots/{SLOT}/approve",
                     {"action": "approved", "request_id": req_id})
            print("  approve response:", str(r)[:200])
            approved = True
        except Exception as e:
            print("  approve ERROR:", repr(e)[:250])
        break

print("\n=== 4) state after approval ===")
time.sleep(6)
slot = get(f"/api/chat/slots/{SLOT}")
print("running:", slot.get("running"), "| pending:", slot.get("pending_approval"),
      "| messages:", slot.get("messages"), "| last:", str(slot.get("last_message"))[:150])

print("\n=== RESULT ===")
print("Was the approval resolved programmatically:", approved)
