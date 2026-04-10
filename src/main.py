"""FastAPI entrypoint: run Apify actors and return dataset rows (no app database)."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv

from apify_client import ApifyClient
from apify_client.errors import ApifyApiError
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.catalog import ScraperSpec, get_scraper, list_scrapers
from src.error_util import gateway_error_payload
from src.schemas import (
    RunAsyncResponse,
    RunBody,
    RunSyncResponse,
    ScraperListResponse,
    ScraperSummary,
    ServiceInfo,
)

logger = logging.getLogger(__name__)

# Load shop-intel-gateway/.env for local dev (never commit .env). On Render, use dashboard env vars.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
RAPIDAPI_PROXY_SECRET = os.environ.get("RAPIDAPI_PROXY_SECRET")


def _require_apify_token() -> None:
    if not APIFY_TOKEN:
        raise RuntimeError("APIFY_TOKEN is not set")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _require_apify_token()
    logging.basicConfig(level=logging.INFO)
    yield


DESCRIPTION = """
## Shop Intel gateway

Runs **Apify actors** from `src/catalog.py` and returns each run’s **default dataset** rows.
**One `APIFY_TOKEN` on the server** backs every scraper; API consumers use **RapidAPI** only.

### RapidAPI (per-usage)

- Publish **one RapidAPI endpoint per scraper** (different paths → different meters / prices), e.g.
  `POST /v1/run/instagram` vs `POST /v1/run/metaAdLibrary`.
- This service does not implement billing; **RapidAPI** charges per request to each operation.

### Authentication (optional)

If `RAPIDAPI_PROXY_SECRET` is set, routes under the API router require header **`X-RapidAPI-Proxy-Secret`**
matching that value. **`GET /`** and **`GET /health`** stay public (e.g. Render health checks).

### Responses

- Success run: `ok: true`, plus `scraperKey`, `actorId`, `runId`, `status`, `items`, `itemCount`.
- Errors: `ok: false`, `error.code`, `error.message`, optional `scraperKey`.
""".strip()

app = FastAPI(
    title="Shop Intel Gateway",
    description=DESCRIPTION,
    version="1.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "meta", "description": "Service info and health."},
        {"name": "scrapers", "description": "Catalog: one entry per logical scraper / RapidAPI endpoint."},
        {"name": "runs", "description": "Execute a scraper (sync = wait + dataset; async = start only)."},
    ],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    body = gateway_error_payload(exc.status_code, exc.detail, request.url.path)
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    msg = exc.errors()[0]["msg"] if exc.errors() else "Validation error"
    detail = {"code": "VALIDATION_ERROR", "message": msg}
    body = gateway_error_payload(422, detail, request.url.path)
    return JSONResponse(status_code=422, content=body)


def _run_field(run: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in run and run[k] is not None:
            return run[k]
    return None


def get_apify_client() -> ApifyClient:
    if not APIFY_TOKEN:
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": "Server misconfiguration: APIFY_TOKEN missing"},
        )
    return ApifyClient(APIFY_TOKEN)


def verify_rapidapi(
    x_rapidapi_proxy_secret: Annotated[str | None, Header()] = None,
) -> None:
    if not RAPIDAPI_PROXY_SECRET:
        return
    if x_rapidapi_proxy_secret != RAPIDAPI_PROXY_SECRET:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Invalid or missing X-RapidAPI-Proxy-Secret"},
        )


RapidApiVerified = Annotated[None, Depends(verify_rapidapi)]
ApifyClientDep = Annotated[ApifyClient, Depends(get_apify_client)]


def _spec_to_summary(s: ScraperSpec) -> ScraperSummary:
    return ScraperSummary(
        key=s.key,
        title=s.title,
        description=s.description,
        category=s.category,
        actorId=s.actor_id,
        exampleInput=s.example_input,
        apifyStoreUrl=s.apify_store_url,
    )


api_router = APIRouter(dependencies=[Depends(verify_rapidapi)])


@api_router.get("/scrapers", response_model=ScraperListResponse, tags=["scrapers"])
def scrapers_list() -> ScraperListResponse:
    return ScraperListResponse(scrapers=[_spec_to_summary(s) for s in list_scrapers()])


@api_router.get("/scrapers/{scraper_key}", response_model=ScraperSummary, tags=["scrapers"])
def scraper_detail(scraper_key: str) -> ScraperSummary:
    spec = get_scraper(scraper_key)
    if not spec:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "UNKNOWN_SCRAPER",
                "message": "Unknown scraper",
                "key": scraper_key,
            },
        )
    return _spec_to_summary(spec)


@api_router.post(
    "/run/{scraper_key}",
    response_model=RunSyncResponse,
    tags=["runs"],
    summary="Run scraper and wait for results",
    responses={404: {"description": "Unknown scraper"}, 502: {"description": "Apify API error"}},
)
def run_sync(
    scraper_key: str,
    body: RunBody,
    client: ApifyClientDep,
) -> RunSyncResponse:
    spec = get_scraper(scraper_key)
    if not spec:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "UNKNOWN_SCRAPER",
                "message": "Unknown scraper",
                "key": scraper_key,
            },
        )

    run_input = body.input if body.input else None
    try:
        run = client.actor(spec.actor_id).call(run_input=run_input)
    except ApifyApiError as e:
        logger.exception("Apify actor call failed")
        raise HTTPException(
            status_code=502,
            detail={"code": "APIFY_ERROR", "message": e.message or "Actor run failed"},
        ) from e
    except Exception as e:
        logger.exception("Actor run failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": str(e)},
        ) from e

    if not run:
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": "Actor run returned no result"},
        )

    ds_id = _run_field(run, "defaultDatasetId", "default_dataset_id")
    if not ds_id:
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": "Run has no default dataset"},
        )

    try:
        page = client.dataset(ds_id).list_items()
        items = list(page.items)
    except Exception as e:
        logger.exception("Dataset list failed")
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": str(e)},
        ) from e

    return RunSyncResponse(
        scraperKey=spec.key,
        actorId=spec.actor_id,
        runId=_run_field(run, "id"),
        status=_run_field(run, "status"),
        itemCount=len(items),
        items=items,
    )


@api_router.post(
    "/run-async/{scraper_key}",
    response_model=RunAsyncResponse,
    status_code=202,
    tags=["runs"],
    summary="Start scraper run (async)",
    responses={404: {"description": "Unknown scraper"}, 502: {"description": "Apify API error"}},
)
def run_async(
    scraper_key: str,
    body: RunBody,
    client: ApifyClientDep,
) -> RunAsyncResponse:
    spec = get_scraper(scraper_key)
    if not spec:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "UNKNOWN_SCRAPER",
                "message": "Unknown scraper",
                "key": scraper_key,
            },
        )

    run_input = body.input if body.input else None
    try:
        run = client.actor(spec.actor_id).start(run_input=run_input)
    except ApifyApiError as e:
        logger.exception("Apify actor start failed")
        raise HTTPException(
            status_code=502,
            detail={"code": "APIFY_ERROR", "message": e.message or "Failed to start actor"},
        ) from e
    except Exception as e:
        logger.exception("Failed to start actor")
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": str(e)},
        ) from e

    if not run:
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL_ERROR", "message": "Actor start returned no result"},
        )

    return RunAsyncResponse(
        scraperKey=spec.key,
        actorId=spec.actor_id,
        runId=_run_field(run, "id"),
        status=_run_field(run, "status"),
        defaultDatasetId=_run_field(run, "defaultDatasetId", "default_dataset_id"),
    )


app.include_router(api_router)
app.include_router(api_router, prefix="/v1")


@app.get("/", response_model=ServiceInfo, tags=["meta"])
def root() -> ServiceInfo:
    return ServiceInfo(
        service="shop-intel-gateway",
        version=app.version,
        docs={
            "swagger": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
            "apiUnversioned": "/scrapers, /run/{key}, …",
            "apiV1": "/v1/scrapers, /v1/run/{key}, …",
        },
    )


@app.get("/health", tags=["meta"])
def health() -> dict[str, bool]:
    return {"ok": True}
