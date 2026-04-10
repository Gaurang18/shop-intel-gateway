"""Live integration tests against Apify (slow; uses real quota).

Run in isolation with a real token:

  cd shop-intel-gateway
  export APIFY_TOKEN='apify_api_...'
  export RUN_LIVE_SCRAPER_TESTS=1
  pip install -r requirements.txt -r requirements-dev.txt
  pytest tests/test_live_scrapers.py -v --tb=short

`whatsapp` is **excluded** here (requires QR / linked device in Apify Live view).

If `APIFY_TOKEN` is unset, tests are skipped. After unit tests that use a mock
token, run this file in a **separate** pytest invocation so `src.main` reloads
with your real token.
"""

from __future__ import annotations

import importlib
import os

import pytest

pytest.importorskip("httpx")

from src.catalog import list_scrapers_automated_live


def _have_live_token() -> bool:
    t = os.getenv("APIFY_TOKEN")
    return bool(t and t != "test-apify-token")


def _live_tests_enabled() -> bool:
    """Avoid slow real Apify runs during normal `pytest` when the token is in the environment."""
    return os.getenv("RUN_LIVE_SCRAPER_TESTS", "").strip() == "1"


pytestmark = pytest.mark.skipif(
    not _live_tests_enabled() or not _have_live_token(),
    reason="Set RUN_LIVE_SCRAPER_TESTS=1 and a real APIFY_TOKEN to run live Apify tests.",
)


@pytest.fixture
def live_client():
    import src.main as main_mod

    importlib.reload(main_mod)
    from fastapi.testclient import TestClient

    with TestClient(main_mod.app) as c:
        yield c


@pytest.mark.parametrize("key", [s.key for s in list_scrapers_automated_live()])
def test_live_run_sync_returns_dataset(live_client, key: str) -> None:
    from src.catalog import get_scraper

    spec = get_scraper(key)
    assert spec is not None
    r = live_client.post(f"/run/{key}", json={"input": spec.example_input})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    assert data.get("scraperKey") == key
    assert data.get("actorId") == spec.actor_id
    assert data.get("status") == "SUCCEEDED", data
    assert "runId" in data and data["runId"]
    assert isinstance(data.get("items"), list)
    assert data.get("itemCount") == len(data["items"])
