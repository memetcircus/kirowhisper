"""Minimal Crew Gateway REST istemcisi — auth query ?token= ile.
Token'ı `kirocrew token` çıktısından okur. Sadece spike doğrulaması için.
"""
import json
import subprocess
import urllib.request
import urllib.parse

BASE = "http://localhost:5476"


def get_token() -> str:
    out = subprocess.check_output(["kirocrew", "token"], text=True).strip()
    # format: http://localhost:5476?token=XXX
    return out.split("token=", 1)[1].strip()


_TOKEN = None


def _url(path: str) -> str:
    global _TOKEN
    if _TOKEN is None:
        _TOKEN = get_token()
    sep = "&" if "?" in path else "?"
    return f"{BASE}{path}{sep}token={_TOKEN}"


def get(path: str):
    req = urllib.request.Request(_url(path), method="GET")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def post(path: str, body: dict):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        _url(path), data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip() else {}
