"""Spike adım 1: Gateway'e bağlan ve ping/status al.
Auth stratejisi: loopback secret'ı (~/.kiro/crew/run/gateway-5476.secret veya
.local_secret) token olarak dene. Client loopback'te token'sız da denenebilir.
"""
import asyncio
import os
from pathlib import Path
from kirocrew_client import KiroCrewClient

CREW_HOME = Path(os.environ.get("KIROCREW_HOME", str(Path.home() / ".kiro" / "crew")))


def read_secret() -> str:
    # Gateway'in kendi secret'ı (port-bazlı) en olası token kaynağı
    for candidate in [
        CREW_HOME / "run" / "gateway-5476.secret",
        CREW_HOME / ".local_secret",
    ]:
        try:
            val = candidate.read_text(encoding="utf-8").strip()
            if val:
                print(f"[secret] okundu: {candidate.name} (len={len(val)})")
                return val
        except OSError:
            pass
    print("[secret] hiçbir secret dosyası okunamadı")
    return ""


async def main():
    token = read_secret()
    # Önce token ile dene
    async with KiroCrewClient(base_url="http://localhost:5476", token=token) as mc:
        print("\n--- ping (token ile) ---")
        try:
            ok = await mc.ping()
            print("ping:", ok)
            if ok:
                status = await mc.get_status()
                print("status:", str(status)[:400])
                return
        except Exception as e:
            print("token ile hata:", repr(e)[:300])

    # Token çalışmazsa token'sız (loopback) dene
    async with KiroCrewClient(base_url="http://localhost:5476") as mc2:
        print("\n--- ping (token'sIZ, loopback) ---")
        try:
            ok = await mc2.ping()
            print("ping:", ok)
            if ok:
                status = await mc2.get_status()
                print("status:", str(status)[:400])
        except Exception as e:
            print("token'sIZ hata:", repr(e)[:300])


if __name__ == "__main__":
    asyncio.run(main())
