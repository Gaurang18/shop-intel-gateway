"""Pydantic models for request/response and OpenAPI (RapidAPI-friendly shapes)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RunBody(BaseModel):
    """Body for `POST .../run` and `POST .../run-async`.

    The gateway **does not validate** fields: whatever JSON you put in `input` is sent to Apify
    as `runInput`. Any combination of properties the actor accepts will work; invalid shapes fail
    at Apify with their error response. Use **`GET /v1/{scraperKey}/input-json-schema`** for the
    actor’s authoritative JSON Schema (from Apify’s default build).
    """

    input: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Arbitrary JSON object forwarded to Apify as `runInput` (all supported actor fields "
            "and combinations are allowed)."
        ),
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


class ScraperHealthResponse(BaseModel):
    """Per-scraper liveness (no Apify call). Use for RapidAPI health checks per product."""

    ok: Literal[True] = True
    scraperKey: str
    title: str


class ActorInputSchemaResponse(BaseModel):
    """JSON Schema for run `input`, as published by Apify for the actor’s default build."""

    ok: Literal[True] = True
    scraperKey: str
    actorId: str
    inputSchema: Any | None = Field(
        default=None,
        description="Parsed JSON Schema for the `input` object in `POST .../run` (may be null if Apify omits it).",
    )
    buildNumber: float | int | None = None
    actVersion: str | None = None
    apifyStoreUrl: str


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
                "Prefer per-scraper paths (e.g. POST /v1/instagram/run vs POST /v1/googleNews/run) "
                "or legacy POST /v1/run/{key}; use distinct operations to price independently."
            ),
            "apifyToken": (
                "A single APIFY_TOKEN on this server calls Apify for all scrapers. "
                "Subscribers only use the RapidAPI key; they never receive your Apify token."
            ),
            "stablePaths": "Prefer versioned paths under /v1/ for new integrations.",
        },
    )
