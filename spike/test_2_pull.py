"""Spike adım 2 (PULL): bir görev başlat, durumunu programatik oku.
"Kiro ne durumda?" akışının temeli.
"""
import time
import crew_rest as crew

print("=== 1) status ===")
st = crew.get("/api/status")
print("uptime:", st.get("uptime"), "| sessions:", st.get("sessions"),
      "| subagents:", st.get("subagents"))

print("\n=== 2) spawn: küçük bir görev başlat ===")
res = crew.post("/api/spawn", {"task": "Reply with exactly: PONG. Nothing else."})
task_id = res.get("id", "")
print("spawn yanıtı:", res)
print("task_id:", task_id)

if not task_id:
    print("!! task_id alınamadı, dur.")
    raise SystemExit(1)

print("\n=== 3) durumu birkaç kez yokla (get_task_result / spawn/<id>) ===")
for i in range(12):
    time.sleep(5)
    try:
        r = crew.get(f"/api/spawn/{task_id}")
        status = r.get("status") or r.get("state") or "?"
        print(f"[{i*5:>3}s] status={status} | keys={list(r.keys())}")
        # sonuç geldiyse göster ve bitir
        if status in ("done", "complete", "completed", "finished", "error", "failed"):
            print("\n--- SONUÇ ---")
            print(json._dumps(r) if False else str(r)[:800])
            break
    except Exception as e:
        print(f"[{i*5:>3}s] hata: {repr(e)[:200]}")

print("\n=== 4) list_subagents (genel görünüm) ===")
try:
    subs = crew.get("/api/spawn")
    print("subagent sayısı:", len(subs) if isinstance(subs, list) else subs)
    if isinstance(subs, list) and subs:
        print("ilk subagent:", str(subs[0])[:400])
except Exception as e:
    print("hata:", repr(e)[:200])
