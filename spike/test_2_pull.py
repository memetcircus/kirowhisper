"""Spike step 2 (PULL): start a task, read its status programmatically.
The basis of the "what's Kiro up to?" flow.
"""
import time
import crew_rest as crew

print("=== 1) status ===")
st = crew.get("/api/status")
print("uptime:", st.get("uptime"), "| sessions:", st.get("sessions"),
      "| subagents:", st.get("subagents"))

print("\n=== 2) spawn: start a small task ===")
res = crew.post("/api/spawn", {"task": "Reply with exactly: PONG. Nothing else."})
task_id = res.get("id", "")
print("spawn response:", res)
print("task_id:", task_id)

if not task_id:
    print("!! no task_id, stopping.")
    raise SystemExit(1)

print("\n=== 3) poll status a few times (get_task_result / spawn/<id>) ===")
for i in range(12):
    time.sleep(5)
    try:
        r = crew.get(f"/api/spawn/{task_id}")
        status = r.get("status") or r.get("state") or "?"
        print(f"[{i*5:>3}s] status={status} | keys={list(r.keys())}")
        # if a result arrived, show it and stop
        if status in ("done", "complete", "completed", "finished", "error", "failed"):
            print("\n--- RESULT ---")
            print(str(r)[:800])
            break
    except Exception as e:
        print(f"[{i*5:>3}s] error: {repr(e)[:200]}")

print("\n=== 4) list_subagents (overview) ===")
try:
    subs = crew.get("/api/spawn")
    print("subagent count:", len(subs) if isinstance(subs, list) else subs)
    if isinstance(subs, list) and subs:
        print("first subagent:", str(subs[0])[:400])
except Exception as e:
    print("error:", repr(e)[:200])
