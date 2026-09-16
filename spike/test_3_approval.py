"""Spike adım 3 (ONAY - projenin kalbi):
Bir chat slot'unda tool gerektiren görev başlat -> pending approval oku ->
POST /api/chat/slots/{slot}/approve ile çöz -> devam ettiğini gör.

Auth: query ?token=  (kirocrew token'dan)
Dashboard-only endpoint'ler için Origin header ZORUNLU.
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
    """POST ateşle, yanıtı bekleme (chat gibi uzun-yaşayan istekler için)."""
    import socket
    req = urllib.request.Request(_u(path), data=json.dumps(body).encode(),
                                 method="POST", headers=HEADERS)
    try:
        urllib.request.urlopen(req, timeout=3)
    except (socket.timeout, urllib.error.URLError, TimeoutError):
        pass  # cevabı beklemiyoruz; agent arka planda çalışmaya devam eder


SLOT = "spike-approval-test"

print("=== 1) slot oluştur ===")
try:
    s = post("/api/chat/slots", {"name": SLOT})
    print("slot:", s.get("key"))
except Exception as e:
    print("slot zaten var olabilir:", repr(e)[:120])

print("\n=== 2) tool gerektiren bir görev gönder ===")
# Dosya yazma / komut çalıştırma tool onayı tetikler
fire("/api/chat", {"slot": SLOT,
                   "message": "Create a file named spike_hello.txt containing the text HELLO. Use your file tools."})
print("mesaj ateşlendi (yanıt beklenmedi), tool onayını bekliyoruz...")

print("\n=== 3) pending approval'i yokla ===")
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
        print(f"\n  >>> ONAY BEKLENIYOR: tool={tool} request_id={req_id}")
        print("  >>> approve gönderiliyor...")
        try:
            r = post(f"/api/chat/slots/{SLOT}/approve",
                     {"action": "approve", "request_id": req_id})
            print("  approve yanıtı:", str(r)[:200])
            approved = True
        except Exception as e:
            print("  approve HATA:", repr(e)[:250])
        break

print("\n=== 4) onay sonrası durum ===")
time.sleep(6)
slot = get(f"/api/chat/slots/{SLOT}")
print("running:", slot.get("running"), "| pending:", slot.get("pending_approval"),
      "| messages:", slot.get("messages"), "| last:", str(slot.get("last_message"))[:150])

print("\n=== SONUÇ ===")
print("Approval programatik çözüldü mü:", approved)
