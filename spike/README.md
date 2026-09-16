# Crew Spike — feasibility proof

One-off exploration scripts that verify programmatic access to the Kiro Crew
Gateway and the **human-in-the-loop approval** flow. NOT product code — written to
prove that KiroWhisper is technically feasible.

## What was proven
- `test_1_connect.py` — Gateway connection (auth investigation).
- `test_2_pull.py` — `spawn` + reading status (PULL / "what's Kiro up to?").
- `test_3_approval.py` / `test_3b_resolve.py` — finding + resolving a pending approval.
- `test_4_e2e.py` — **END TO END:** task -> catch approval -> programmatic approve ->
  the file actually got created. Proof of the project's heart.

## Running (requires a local Crew Gateway)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install aiohttp    # for test_1; the others use only stdlib + `kirocrew token`
python3 test_4_e2e.py
```

## Findings
Auth: `kirocrew token` -> JWT -> requests carry `?token=<JWT>` query param + `Origin` header.
Resolve approval: `POST /api/chat/slots/<slot>/approve {"action":"approved","request_id":...}`.
Critical gotcha: `action` must be **"approved"** (past tense); "approve" silently rejects.

> Note: these scripts contain NO secret values; the token is fetched at runtime
> from `kirocrew token`.
