"""Unit tests for error path helpers."""

from __future__ import annotations

from src.error_util import scraper_key_from_path


def test_scraper_key_from_prefixed_and_legacy_paths() -> None:
    assert scraper_key_from_path("/v1/instagram/run") == "instagram"
    assert scraper_key_from_path("/v1/metaAdLibrary/run-async") == "metaAdLibrary"
    assert scraper_key_from_path("/googleNews/run") == "googleNews"
    assert scraper_key_from_path("/run/instagram") == "instagram"
    assert scraper_key_from_path("/v1/run/instagram") == "instagram"
    assert scraper_key_from_path("/run-async/googleNews") == "googleNews"
    assert scraper_key_from_path("/instagram/health") is None
    assert scraper_key_from_path("/v1/instagram/input-json-schema") is None
    assert scraper_key_from_path("/v1/scrapers") is None
