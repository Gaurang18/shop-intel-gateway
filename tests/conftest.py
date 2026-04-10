"""Reload `src.main` after env changes so module-level settings apply."""

from __future__ import annotations

import importlib
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def configure_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Return a function that sets env vars and reloads `src.main`."""

    def _configure(
        *,
        apify_token: str = "test-apify-token",
        rapidapi_secret: str | None = None,
    ):
        monkeypatch.setenv("APIFY_TOKEN", apify_token)
        if rapidapi_secret is None:
            monkeypatch.delenv("RAPIDAPI_PROXY_SECRET", raising=False)
        else:
            monkeypatch.setenv("RAPIDAPI_PROXY_SECRET", rapidapi_secret)
        import src.main as main

        importlib.reload(main)
        return main

    return _configure


@pytest.fixture
def client(configure_env: Any) -> Generator[TestClient, None, None]:
    main = configure_env()
    with TestClient(main.app) as tc:
        yield tc
    main.app.dependency_overrides.clear()
