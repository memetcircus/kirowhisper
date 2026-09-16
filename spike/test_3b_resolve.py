"""Spike 3b: slot mesajlarından bekleyen permission'i (approval_id) oku ve
/api/chat/slots/{slot}/approve ile ONAYLA. Sonra dosya gerçekten oluştu mu bak.
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


print("=== bekleyen onayı bul ===")
aid, content, meta = find_pending_approval()
print("approval_id:", aid)
print("tool:", content)
print("purpose/input:", str(meta.get("tool_input"))[:120] if meta else None,
      "| read_only:", meta.get("is_read_only") if meta else None,
      "| shell:", meta.get("is_shell") if meta else None)

if not aid:
    print("!! bekleyen onay yok (belki timeout'la deny oldu). Dur.")
    raise SystemExit(0)

print("\n=== APPROVE gönder (action=approve, request_id=approval_id) ===")
try:
    r = post(f"/api/chat/slots/{SLOT}/approve", {"action": "approve", "request_id": aid})
    print("approve yanıtı:", str(r)[:250])
except Exception as e:
    print("approve HATA:", repr(e)[:300])

print("\n=== 8sn bekle, dosya gerçekten oluştu mu? ===")
time.sleep(8)
f = Path.home() / ".kiro" / "crew" / "workspace" / "spike_hello.txt"
print("dosya var mı:", f.exists())
if f.exists():
    print("içerik:", repr(f.read_text()))

slot = get(f"/api/chat/slots/{SLOT}")
print("running:", slot.get("running"))
# son tool/asistan mesajı
for m in reversed(slot.get("messages", [])):
    if m.get("role") in ("assistant", "tool"):
        print("son mesaj:", m.get("role"), "->", str(m.get("content"))[:150])
        break
