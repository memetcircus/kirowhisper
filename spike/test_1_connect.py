"""Spike step 1: connect to the Gateway and get ping/status.
Auth strategy: try the loopback secret (~/.kiro/crew/run/gateway-5476.secret or
.local_secret) as a token. The client may also work token-less on loopback.
"""
import asyncio
import os
from pathlib import Path
from kirocrew_client import KiroCrewClient

CREW_HOME = Path(os.environ.get("KIROCREW_HOME", str(Path.home() / ".kiro" / "crew")))


def read_secret() -> str:
    # The Gateway's own (port-based) secret is the most likely token source
    for candidate in [
        CREW_HOME / "run" / "gateway-5476.secret",
        CREW_HOME / ".local_secret",
    ]:
        try:
            val = candidate.read_text(encoding="utf-8").strip()
            if val:
                print(f"[secret] read: {candidate.name} (len={len(val)})")
                return val
        except OSError:
            pass
    print("[secret] no secret file could be read")
    return ""


async def main():
    token = read_secret()
    # Try with token first
    async with KiroCrewClient(base_url="http://localhost:5476", token=token) as mc:
        print("\n--- ping (with token) ---")
        try:
            ok = await mc.ping()
            print("ping:", ok)
            if ok:
                status = await mc.get_status()
                print("status:", str(status)[:400])
                return
        except Exception as e:
            print("error with token:", repr(e)[:300])

    # If the token fails, try token-less (loopback)
    async with KiroCrewClient(base_url="http://localhost:5476") as mc2:
        print("\n--- ping (token-LESS, loopback) ---")
        try:
            ok = await mc2.ping()
            print("ping:", ok)
            if ok:
                status = await mc2.get_status()
                print("status:", str(status)[:400])
        except Exception as e:
            print("error token-LESS:", repr(e)[:300])


if __name__ == "__main__":
    asyncio.run(main())
