#!/usr/bin/env python3
"""Run catalog scrapers through the gateway (same paths as production).

Usage (from repo root `shop-intel-gateway/`):

  export APIFY_TOKEN='apify_api_...'
  python scripts/verify_scrapers.py

By default, **whatsapp** is skipped (needs QR code in Apify Live view). To attempt it:

  VERIFY_WHATSAPP=1 python scripts/verify_scrapers.py

Requires `pip install -r requirements.txt` and `httpx` (see `requirements-dev.txt`).

Exits 0 only if each **executed** scraper returns HTTP 200, `status` SUCCEEDED, and items are consistent.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    token = os.getenv("APIFY_TOKEN")
    if not token:
        print("error: set APIFY_TOKEN in the environment", file=sys.stderr)
        return 1
    if token == "test-apify-token":
        print("error: refusing to run with the pytest mock token", file=sys.stderr)
        return 1

    os.environ.pop("RAPIDAPI_PROXY_SECRET", None)

    try:
        from fastapi.testclient import TestClient
    except ModuleNotFoundError:
        print("error: install httpx (e.g. pip install httpx)", file=sys.stderr)
        return 1

    import src.main as main_mod

    importlib.reload(main_mod)

    from src.catalog import get_scraper, list_scrapers

    failures = 0
    skipped = 0
    ran = 0

    with TestClient(main_mod.app) as client:
        for spec in list_scrapers():
            if not spec.automated_live_ok and os.environ.get("VERIFY_WHATSAPP") != "1":
                print(
                    f"\n=== {spec.key} → SKIPPED (manual WhatsApp session; VERIFY_WHATSAPP=1 to try) ===",
                    flush=True,
                )
                skipped += 1
                continue

            ran += 1
            print(f"\n=== {spec.key} → {spec.actor_id} ===", flush=True)
            r = client.post(f"/run/{spec.key}", json={"input": spec.example_input})
            print(f"HTTP {r.status_code}", flush=True)
            if r.status_code != 200:
                print(r.text[:4000], file=sys.stderr)
                failures += 1
                continue
            data = r.json()
            if data.get("ok") is not True:
                print(f"error: expected ok: true, got {data!r}", file=sys.stderr)
                failures += 1
                continue
            if data.get("scraperKey") != spec.key or data.get("actorId") != spec.actor_id:
                print("error: scraperKey/actorId mismatch with catalog", file=sys.stderr)
                failures += 1
                continue
            status = data.get("status")
            items = data.get("items")
            n = data.get("itemCount")
            print(f"runId={data.get('runId')} status={status} itemCount={n}", flush=True)
            if status != "SUCCEEDED":
                print(f"error: expected SUCCEEDED, got {status!r}", file=sys.stderr)
                failures += 1
                continue
            if not isinstance(items, list) or n != len(items):
                print("error: items must be a list and itemCount must match length", file=sys.stderr)
                failures += 1
                continue
            if n > 0 and items:
                print(f"first item keys: {list(items[0].keys())[:12]}", flush=True)

        if failures == 0 and ran > 0:
            ig = get_scraper("instagram")
            probe_body = {"input": ig.example_input} if ig else {"input": {}}
            probe = client.post("/v1/run/instagram", json=probe_body)
            if probe.status_code != 200 or probe.json().get("ok") is not True:
                print("error: /v1/run/instagram should match unversioned path", file=sys.stderr)
                failures += 1

    if failures:
        print(f"\nFailed: {failures} run(s)", file=sys.stderr)
        return 1
    print(f"\nOK: {ran} scraper run(s) checked; {skipped} skipped.", flush=True)
    if ran:
        print("/v1/run/instagram probe OK.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
