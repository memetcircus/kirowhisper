"""Spike 4: UÇTAN UCA tek akış.
Görev ateşle -> permission'i HIZLI yakala -> deny-timeout'tan ÖNCE approve ->
dosya GERÇEKTEN oluşuyor mu?  (approval mekanizmasının tam kanıtı)
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
    # EN SON permission mesajını al (geçmişteki eskiyi değil)
    for m in reversed(slot.get("messages", [])):
        if m.get("role") == "permission":
            meta = m.get("meta", {})
            aid = meta.get("approval_id") or meta.get("request_id")
            if aid:
                return aid, m.get("content", "")
    return None, None


# temizlik: dosyayı ve ESKİ slot'u sil, taze başla
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

print("=== görev ateşle ===")
fire("/api/chat", {"slot": SLOT,
                   "message": "Create a file named spike_e2e.txt containing exactly: WORKS. Use file tools."})

print("=== permission'i HIZLI yakala (1sn aralık) ===")
aid = None
for i in range(40):
    time.sleep(1)
    aid, tool = pending_approval()
    if aid:
        print(f"[{i}s] YAKALANDI: {tool}  aid={aid}")
        break
    if i % 5 == 0:
        print(f"[{i}s] henüz onay yok...")

if not aid:
    print("!! onay yakalanamadı"); raise SystemExit(1)

print("=== HEMEN approve ===")
r = post(f"/api/chat/slots/{SLOT}/approve", {"action": "approved", "request_id": aid})
print("approve:", r)

print("=== dosya oluşuyor mu? (10sn izle) ===")
for i in range(10):
    time.sleep(1)
    if TARGET.exists():
        print(f"[{i}s] ✅ DOSYA OLUŞTU! içerik: {TARGET.read_text()!r}")
        break
else:
    print("dosya hâlâ yok")

print("\n=== SON ASISTAN MESAJI ===")
slot = get(f"/api/chat/slots/{SLOT}")
for m in reversed(slot.get("messages", [])):
    if m.get("role") == "assistant":
        print(str(m.get("content"))[:200]); break
