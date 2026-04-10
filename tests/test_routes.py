"""Route tests with mocked Apify client (no real Apify calls)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.catalog import SCRAPERS, get_scraper, list_scrapers_automated_live


def _scraper_keys() -> set[str]:
    return {s.key for s in SCRAPERS}


def test_root_and_health(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "shop-intel-gateway"
    assert "/docs" in body["docs"]["swagger"]
    assert "rapidApi" in body
    assert "usageBilling" in body["rapidApi"]
    assert "/v1/" in body["docs"]["apiV1"]

    h = client.get("/health")
    assert h.status_code == 200
    assert h.json() == {"ok": True}


def test_whatsapp_excluded_from_automated_live() -> None:
    wa = get_scraper("whatsapp")
    assert wa is not None
    assert wa.automated_live_ok is False
    auto_keys = {s.key for s in list_scrapers_automated_live()}
    assert "whatsapp" not in auto_keys
    assert "instagram" in auto_keys


def test_list_scrapers(client: TestClient) -> None:
    r = client.get("/scrapers")
    assert r.status_code == 200
    data = r.json()
    keys = {s["key"] for s in data["scrapers"]}
    assert keys == _scraper_keys()


def test_scraper_detail_ok(client: TestClient) -> None:
    r = client.get("/scrapers/instagram")
    assert r.status_code == 200
    assert r.json()["actorId"] == "apify/instagram-scraper"


def test_scraper_detail_unknown(client: TestClient) -> None:
    r = client.get("/scrapers/doesNotExist")
    assert r.status_code == 404


def test_run_unknown_scraper(client: TestClient) -> None:
    r = client.post("/run/unknown", json={"input": {}})
    assert r.status_code == 404
    err = r.json()
    assert err["ok"] is False
    assert err["error"]["code"] == "UNKNOWN_SCRAPER"
    assert err["scraperKey"] == "unknown"


def test_input_json_schema(client: TestClient) -> None:
    import src.main as main

    mock_get = MagicMock(
        return_value={
            "inputSchema": '{"type": "object", "title": "In"}',
            "buildNumber": 42,
            "actVersion": "1.0.0",
        }
    )
    mock_default_build = MagicMock()
    mock_default_build.get = mock_get
    mock_actor_res = MagicMock()
    mock_actor_res.default_build = MagicMock(return_value=mock_default_build)
    mock_client = MagicMock()
    mock_client.actor = MagicMock(return_value=mock_actor_res)

    main.app.dependency_overrides[main.get_apify_client] = lambda: mock_client
    try:
        r = client.get("/v1/instagram/input-json-schema")
    finally:
        main.app.dependency_overrides.clear()

    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["scraperKey"] == "instagram"
    assert data["inputSchema"]["type"] == "object"
    mock_client.actor.assert_called_once_with("apify/instagram-scraper")


def test_per_scraper_health_and_info(client: TestClient) -> None:
    h = client.get("/instagram/health")
    assert h.status_code == 200
    assert h.json() == {"ok": True, "scraperKey": "instagram", "title": "Instagram"}

    i = client.get("/v1/googleNews/info")
    assert i.status_code == 200
    assert i.json()["key"] == "googleNews"
    assert i.json()["actorId"] == "automation-lab/google-news-scraper"


def test_per_scraper_run_matches_legacy_run(client: TestClient) -> None:
    import src.main as main

    mock_client = MagicMock()
    mock_client.actor.return_value.call.return_value = {
        "id": "r-pref",
        "status": "SUCCEEDED",
        "defaultDatasetId": "ds-pref",
    }
    mock_client.dataset.return_value.list_items.return_value = MagicMock(items=[{"a": 1}])

    main.app.dependency_overrides[main.get_apify_client] = lambda: mock_client
    try:
        legacy = client.post("/run/instagram", json={"input": {}})
        prefixed = client.post("/instagram/run", json={"input": {}})
        v1 = client.post("/v1/instagram/run", json={"input": {}})
    finally:
        main.app.dependency_overrides.clear()

    assert legacy.json() == prefixed.json() == v1.json()
    assert legacy.status_code == 200


def test_v1_paths_match_unversioned_run(client: TestClient) -> None:
    import src.main as main

    mock_client = MagicMock()
    mock_client.actor.return_value.call.return_value = {
        "id": "r-v1",
        "status": "SUCCEEDED",
        "defaultDatasetId": "ds-v1",
    }
    mock_client.dataset.return_value.list_items.return_value = MagicMock(items=[{"x": 1}])

    main.app.dependency_overrides[main.get_apify_client] = lambda: mock_client
    try:
        r1 = client.post("/run/instagram", json={"input": {}})
        r2 = client.post("/v1/run/instagram", json={"input": {}})
    finally:
        main.app.dependency_overrides.clear()

    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json()


def test_run_sync_success(client: TestClient) -> None:
    import src.main as main

    mock_client = MagicMock()
    mock_client.actor.return_value.call.return_value = {
        "id": "run-xyz",
        "status": "SUCCEEDED",
        "defaultDatasetId": "dataset-1",
    }
    mock_client.dataset.return_value.list_items.return_value = MagicMock(
        items=[{"foo": "bar"}, {"n": 2}],
    )

    main.app.dependency_overrides[main.get_apify_client] = lambda: mock_client
    try:
        r = client.post("/run/instagram", json={"input": {"resultsLimit": 1}})
    finally:
        main.app.dependency_overrides.clear()

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["scraperKey"] == "instagram"
    assert body["actorId"] == "apify/instagram-scraper"
    assert body["runId"] == "run-xyz"
    assert body["status"] == "SUCCEEDED"
    assert body["itemCount"] == 2
    assert body["items"] == [{"foo": "bar"}, {"n": 2}]
    mock_client.actor.assert_called_once_with("apify/instagram-scraper")
    mock_client.actor.return_value.call.assert_called_once_with(run_input={"resultsLimit": 1})


def test_run_async_success(client: TestClient) -> None:
    import src.main as main

    mock_client = MagicMock()
    mock_client.actor.return_value.start.return_value = {
        "id": "run-async-1",
        "status": "READY",
        "defaultDatasetId": "ds-async",
    }

    main.app.dependency_overrides[main.get_apify_client] = lambda: mock_client
    try:
        r = client.post("/run-async/googleNews", json={"input": {}})
    finally:
        main.app.dependency_overrides.clear()

    assert r.status_code == 202
    body = r.json()
    assert body["ok"] is True
    assert body["scraperKey"] == "googleNews"
    assert body["actorId"] == "automation-lab/google-news-scraper"
    assert body["runId"] == "run-async-1"
    assert body["defaultDatasetId"] == "ds-async"


def test_rapidapi_proxy_secret_required(configure_env: Any) -> None:
    main = configure_env(rapidapi_secret="expected-secret")
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        assert c.get("/scrapers").status_code == 401
        assert c.get("/instagram/health").status_code == 401
        assert c.get("/instagram/input-json-schema").status_code == 401
        ok = c.get("/scrapers", headers={"X-RapidAPI-Proxy-Secret": "expected-secret"})
        assert ok.status_code == 200
        assert (
            c.get("/instagram/health", headers={"X-RapidAPI-Proxy-Secret": "expected-secret"}).status_code
            == 200
        )
        assert c.get("/health").status_code == 200
        assert c.get("/").status_code == 200
