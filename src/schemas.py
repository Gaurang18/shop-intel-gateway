"""Pydantic models for request/response and OpenAPI (RapidAPI-friendly shapes)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RunBody(BaseModel):
    """Actor run input (must match the actor schema on Apify)."""

    input: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON object passed to the actor as `runInput`.",
    )


class ScraperSummary(BaseModel):
    """Public metadata for one scraper (no secrets)."""

    key: str
    title: str
    description: str
    category: str
    actorId: str
    exampleInput: dict[str, Any]
    apifyStoreUrl: str


class ScraperListResponse(BaseModel):
    scrapers: list[ScraperSummary]


class RunSyncResponse(BaseModel):
    """Successful sync run: always `ok: true`; `itemCount` equals `len(items)`."""

    ok: Literal[True] = True
    scraperKey: str = Field(description="Catalog key from the URL (your RapidAPI operation path segment).")
    actorId: str = Field(description="Apify actor ID executed for this call.")
    runId: str | None
    status: str | None
    itemCount: int
    items: list[dict[str, Any]]


class RunAsyncResponse(BaseModel):
    """Async run accepted; poll Apify for completion using runId / defaultDatasetId."""

    ok: Literal[True] = True
    scraperKey: str
    actorId: str
    runId: str | None
    status: str | None
    defaultDatasetId: str | None


class GatewayErrorDetail(BaseModel):
    code: str
    message: str
    httpStatus: int


class GatewayErrorResponse(BaseModel):
    """Stable error envelope for programmatic clients (e.g. RapidAPI subscribers)."""

    ok: Literal[False] = False
    scraperKey: str | None = Field(
        default=None,
        description="Populated when the path is a run endpoint; helps correlate billing logs.",
    )
    error: GatewayErrorDetail


class ServiceInfo(BaseModel):
    service: str
    version: str
    docs: dict[str, str]
    rapidApi: dict[str, str] = Field(
        default_factory=lambda: {
            "usageBilling": (
                "RapidAPI counts one request per HTTP call to each published endpoint. "
                "Create a separate RapidAPI operation per scraper (e.g. POST /v1/run/instagram vs "
                "POST /v1/run/googleNews) to price them independently."
            ),
            "apifyToken": (
                "A single APIFY_TOKEN on this server calls Apify for all scrapers. "
                "Subscribers only use the RapidAPI key; they never receive your Apify token."
            ),
            "stablePaths": "Prefer versioned paths under /v1/ for new integrations.",
        },
    )
