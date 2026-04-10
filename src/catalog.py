"""Shop Intel scraper registry: Meta Ads, Instagram, WhatsApp, Google News, Amazon, Places.

Override Apify actor IDs without code changes:

| Environment variable | Default actor |
|----------------------|---------------|
| `APIFY_ACTOR_META_AD_LIBRARY` | `whoareyouanas/meta-ad-scraper` |
| `APIFY_ACTOR_INSTAGRAM` | `apify/instagram-scraper` |
| `APIFY_ACTOR_WHATSAPP` | `curious_coder/whatsapp-scraper` |
| `APIFY_ACTOR_GOOGLE_NEWS` | `automation-lab/google-news-scraper` |
| `APIFY_ACTOR_AMAZON` | `delicious_zebu/amazon-product-details-scraper` |
| `APIFY_ACTOR_GOOGLE_PLACES` | `codingfrontend/google-maps-places-scraper` |
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


def _actor(env_key: str, default_id: str) -> str:
    v = (os.environ.get(env_key) or "").strip()
    return v if v else default_id


@dataclass(frozen=True, slots=True)
class ScraperSpec:
    """One logical scraper = one RapidAPI path segment (`/v1/run/{key}`)."""

    key: str
    actor_id: str
    title: str
    description: str
    category: str
    example_input: dict[str, Any]
    apify_store_url: str
    """If False, skip in `verify_scrapers.py` and live pytest (needs QR / manual session)."""
    automated_live_ok: bool = True


SCRAPERS: tuple[ScraperSpec, ...] = (
    ScraperSpec(
        key="metaAdLibrary",
        actor_id=_actor("APIFY_ACTOR_META_AD_LIBRARY", "whoareyouanas/meta-ad-scraper"),
        title="Meta (Facebook) Ad Library",
        description=(
            "Search Meta Ad Library by keyword and country. "
            "Heavy browser actor; narrow `searchQuery` for tests. "
            "Many flows benefit from residential proxy on Apify (see actor README)."
        ),
        category="ads",
        example_input={
            "searchQuery": "apify",
            "country": "US",
            "activeStatus": "active",
            "adType": "all",
            "mediaType": "all",
            "maxConcurrency": 1,
        },
        apify_store_url="https://apify.com/whoareyouanas/meta-ad-scraper",
    ),
    ScraperSpec(
        key="instagram",
        actor_id=_actor("APIFY_ACTOR_INSTAGRAM", "apify/instagram-scraper"),
        title="Instagram",
        description=(
            "Scrape public Instagram data from profile/hashtag/post URLs. "
            "Uses official Apify Instagram actor; keep `resultsLimit` low for tests."
        ),
        category="social",
        example_input={
            "directUrls": ["https://www.instagram.com/apifytech/"],
            "resultsLimit": 3,
            "addParentData": False,
        },
        apify_store_url="https://apify.com/apify/instagram-scraper",
    ),
    ScraperSpec(
        key="whatsapp",
        actor_id=_actor("APIFY_ACTOR_WHATSAPP", "curious_coder/whatsapp-scraper"),
        title="WhatsApp (business profile lookup)",
        description=(
            "Looks up WhatsApp business/public details for phone numbers. "
            "First-time use requires scanning a QR code in Apify **Live view** (linked device); "
            "then set `sessionStoreId` to reuse the session. **Not suitable for unattended API tests.**"
        ),
        category="social",
        example_input={
            "numbers": ["8976859807"],
            "sessionStoreId": "whatsapp-session-1",
        },
        apify_store_url="https://apify.com/curious_coder/whatsapp-scraper",
        automated_live_ok=False,
    ),
    ScraperSpec(
        key="googleNews",
        actor_id=_actor("APIFY_ACTOR_GOOGLE_NEWS", "automation-lab/google-news-scraper"),
        title="Google News",
        description=(
            "Keyword search on Google News (RSS-backed). "
            "Adjust `queries` and `maxArticles`; see actor page for country/topic options."
        ),
        category="news",
        example_input={
            "queries": ["artificial intelligence"],
            "maxArticles": 5,
        },
        apify_store_url="https://apify.com/automation-lab/google-news-scraper",
    ),
    ScraperSpec(
        key="amazonMarketplace",
        actor_id=_actor("APIFY_ACTOR_AMAZON", "delicious_zebu/amazon-product-details-scraper"),
        title="Amazon marketplace (product details)",
        description=(
            "Product details from Amazon by ASIN or product URL (`Params` array). "
            "Uses US catalog in examples; see actor for other marketplaces."
        ),
        category="ecommerce",
        example_input={
            "Params": ["B00091S3K4"],
        },
        apify_store_url="https://apify.com/delicious_zebu/amazon-product-details-scraper",
    ),
    ScraperSpec(
        key="googlePlaces",
        actor_id=_actor("APIFY_ACTOR_GOOGLE_PLACES", "codingfrontend/google-maps-places-scraper"),
        title="Google Maps / Places",
        description=(
            "Search Google Maps for businesses by string + location. "
            "Tune `maxCrawledPlacesPerSearch` and filters per actor README."
        ),
        category="local",
        example_input={
            "searchStringsArray": ["coffee shop"],
            "locationQuery": "San Francisco, USA",
            "maxCrawledPlacesPerSearch": 3,
            "language": "en",
        },
        apify_store_url="https://apify.com/codingfrontend/google-maps-places-scraper",
    ),
)

_BY_KEY: dict[str, ScraperSpec] = {s.key: s for s in SCRAPERS}


def get_scraper(key: str) -> ScraperSpec | None:
    return _BY_KEY.get(key)


def list_scrapers() -> tuple[ScraperSpec, ...]:
    return SCRAPERS


def list_scrapers_automated_live() -> tuple[ScraperSpec, ...]:
    """Scrapers safe to run in CI / `verify_scrapers` without human interaction."""
    return tuple(s for s in SCRAPERS if s.automated_live_ok)
