"""FastAPI entrypoint: run Apify actors and return dataset rows (no app database)."""

from __future__ import annotations

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from dotenv import load_dotenv

from apify_client import ApifyClient
from apify_client.errors import ApifyApiError
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.routing import APIRoute
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.catalog import ScraperSpec, get_scraper, list_scrapers
from src.error_util import gateway_error_payload
from src.schemas import (
    ActorInputSchemaResponse,
    RunAsyncResponse,
    RunBody,
    RunSyncResponse,
    ScraperHealthResponse,
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

- Prefer **one path prefix per scraper** (separate operations in Swagger), e.g.
  `GET /v1/instagram/health`, `POST /v1/instagram/run`, `GET /v1/metaAdLibrary/health`, …
- Legacy paths `POST /v1/run/{key}` still work. **RapidAPI** meters per HTTP path you publish.

### Authentication (optional)

If `RAPIDAPI_PROXY_SECRET` is set, routes under the API router require header **`X-RapidAPI-Proxy-Secret`**
matching that value. **`GET /`** and **`GET /health`** stay public (e.g. Render health checks).

### Run `input` (Apify)

- **`POST .../run`** bodies use `{ "input": { ... } }`. The gateway **forwards `input` as-is** to Apify
  (no field validation here). Use **`GET /v1/{scraperKey}/input-json-schema`** for the actor’s JSON Schema.

### Responses

- Success run: `ok: true`, plus `scraperKey`, `actorId`, `runId`, `status`, `items`, `itemCount`.
- Errors: `ok: false`, `error.code`, `error.message`, optional `scraperKey`.
""".strip()


def _openapi_operation_id(route: APIRoute) -> str:
    """Stable IDs across duplicate mounts (same router on `/` and `/v1`)."""
    method = next(iter(sorted(route.methods))).lower()
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", route.path.strip("/")).strip("_").lower() or "root"
    while "__" in slug:
        slug = slug.replace("__", "_")
    return f"{method}_{slug}"


app = FastAPI(
    title="Shop Intel Gateway",
    description=DESCRIPTION,
    version="1.4.0",
    lifespan=lifespan,
    generate_unique_id_function=_openapi_operation_id,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "meta", "description": "Service info and global health."},
        {"name": "scrapers", "description": "Catalog: list all scrapers and legacy GET /scrapers/{key}."},
        {"name": "runs", "description": "Legacy: POST /run/{key} and POST /run-async/{key}."},
        *[
            {
                "name": s.key,
                "description": (
                    f"{s.title} — GET /{s.key}/health, /{s.key}/info, /{s.key}/input-json-schema; "
                    f"POST /{s.key}/run, /{s.key}/run-async"
                ),
            }
            for s in list_scrapers()
        ],
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


def _run_sync_core(spec: ScraperSpec, body: RunBody, client: ApifyClient) -> RunSyncResponse:
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


def _run_async_core(spec: ScraperSpec, body: RunBody, client: ApifyClient) -> RunAsyncResponse:
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


def _parse_actor_input_schema(raw: Any) -> Any | None:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return {
                "_gatewayNote": "Apify inputSchema string was not valid JSON",
                "_rawPrefix": s[:2000],
            }
    return raw


def _make_scraper_router(spec: ScraperSpec) -> APIRouter:
    """Dedicated paths per catalog key: /{key}/health, /info, /input-json-schema, /run, /run-async."""
    r = APIRouter(prefix=f"/{spec.key}", tags=[spec.key])

    @r.get(
        "/health",
        response_model=ScraperHealthResponse,
        summary="Health (no Apify call)",
    )
    def scraper_health() -> ScraperHealthResponse:
        return ScraperHealthResponse(scraperKey=spec.key, title=spec.title)

    @r.get(
        "/info",
        response_model=ScraperSummary,
        summary="Scraper metadata",
    )
    def scraper_info() -> ScraperSummary:
        return _spec_to_summary(spec)

    @r.get(
        "/input-json-schema",
        response_model=ActorInputSchemaResponse,
        summary="JSON Schema for run input (Apify default build)",
        responses={502: {"description": "Apify API error"}},
    )
    def scraper_input_json_schema(client: ApifyClientDep) -> ActorInputSchemaResponse:
        try:
            build = client.actor(spec.actor_id).default_build().get()
        except ApifyApiError as e:
            logger.exception("Failed to fetch default build for input schema")
            raise HTTPException(
                status_code=502,
                detail={"code": "APIFY_ERROR", "message": e.message or "Could not load actor build"},
            ) from e
        except Exception as e:
            logger.exception("Actor build fetch failed")
            raise HTTPException(
                status_code=500,
                detail={"code": "INTERNAL_ERROR", "message": str(e)},
            ) from e

        parsed = _parse_actor_input_schema(build.get("inputSchema"))
        act_ver = build.get("actVersion")
        return ActorInputSchemaResponse(
            scraperKey=spec.key,
            actorId=spec.actor_id,
            inputSchema=parsed,
            buildNumber=build.get("buildNumber"),
            actVersion=str(act_ver) if act_ver is not None else None,
            apifyStoreUrl=spec.apify_store_url,
        )

    @r.post(
        "/run",
        response_model=RunSyncResponse,
        summary="Run and wait for dataset",
        description=(
            "Send `{ \"input\": { ... } }`. The gateway forwards `input` to Apify with no validation — "
            "use **GET /input-json-schema** on this scraper for the JSON Schema. "
            "Catalog `exampleInput` is in **GET /info** or **GET /scrapers**."
        ),
        responses={502: {"description": "Apify API error"}},
    )
    def scraper_run_sync(body: RunBody, client: ApifyClientDep) -> RunSyncResponse:
        return _run_sync_core(spec, body, client)

    @r.post(
        "/run-async",
        response_model=RunAsyncResponse,
        status_code=202,
        summary="Start run (async)",
        description=(
            "Same body as **POST …/run**. `input` is passed through to Apify. "
            "See **GET …/input-json-schema** for allowed fields."
        ),
        responses={502: {"description": "Apify API error"}},
    )
    def scraper_run_async(body: RunBody, client: ApifyClientDep) -> RunAsyncResponse:
        return _run_async_core(spec, body, client)

    return r


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
    return _run_sync_core(spec, body, client)


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
    return _run_async_core(spec, body, client)


for _spec in list_scrapers():
    api_router.include_router(_make_scraper_router(_spec))

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
            "perScraper": "/{scraperKey}/health, /info, /input-json-schema, /run, /run-async",
            "apiUnversioned": "/scrapers, /run/{key}, /instagram/…, …",
            "apiV1": "/v1/scrapers, /v1/run/{key}, /v1/instagram/…, …",
        },
    )


@app.get("/health", tags=["meta"])
def health() -> dict[str, bool]:
    return {"ok": True}
