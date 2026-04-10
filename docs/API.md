# Shop Intel Gateway — HTTP API

Base URL: your deployed origin (e.g. `https://shop-intel-gateway.onrender.com`) or `http://127.0.0.1:8000` locally.

**Versioned base (recommended for RapidAPI):** prefix paths with **`/v1`**. Each scraper has its **own path prefix** (e.g. `GET /v1/instagram/health`, `POST /v1/instagram/run`). Legacy `POST /v1/run/{key}` still works. Unversioned mirrors exist for the same paths without `/v1`.

**RapidAPI-focused doc** (all scrapers, endpoints, headers, examples): [`docs/RAPIDAPI.md`](RAPIDAPI.md).

All JSON responses use UTF-8.

### Success (sync run)

`200` — body always includes:

- `ok: true`
- `scraperKey`, `actorId` — which catalog entry ran (aligns with your RapidAPI path)
- `runId`, `status` — Apify run
- `itemCount`, `items` — default dataset rows (`itemCount === items.length`)

### Errors

Structured body (not raw `detail` only):

- `ok: false`
- `scraperKey` — set when the URL is a run endpoint (helps support and logs)
- `error.code`, `error.message`, `error.httpStatus`

## Interactive docs

- **Swagger UI**: `GET /docs`
- **ReDoc**: `GET /redoc`
- **OpenAPI JSON**: `GET /openapi.json`

## Authentication (optional)

If the server has environment variable **`RAPIDAPI_PROXY_SECRET`** set, these routes require header:

```http
X-RapidAPI-Proxy-Secret: <same value as env>
```

**Unaffected** (always public): `GET /`, `GET /health`.

## Endpoints

### `GET /`

Service metadata and links to documentation.

**Response** (`200`)

```json
{
  "service": "shop-intel-gateway",
  "version": "1.4.0",
  "docs": {
    "swagger": "/docs",
    "redoc": "/redoc",
    "openapi": "/openapi.json",
    "perScraper": "/{key}/health, /{key}/info, /{key}/run, /{key}/run-async",
    "apiV1": "/v1/scrapers, /v1/run/{key}, /v1/instagram/…, …"
  },
  "rapidApi": {
    "usageBilling": "…",
    "apifyToken": "…",
    "stablePaths": "…"
  }
}
```

---

### `GET /health`

Load balancer / Render health check. Does not call Apify.

**Response** (`200`)

```json
{ "ok": true }
```

---

## Per-scraper API (recommended for RapidAPI)

For each catalog **`key`** (e.g. `instagram`, `metaAdLibrary`, `googleNews`), these paths exist under **`/v1/{key}/…`** and without `/v1`:

| Method | Path | Purpose |
|--------|------|--------|
| `GET` | `/{key}/health` | Liveness for that scraper only (does **not** call Apify). |
| `GET` | `/{key}/info` | Same metadata as `GET /scrapers/{key}`. |
| `GET` | `/{key}/input-json-schema` | **JSON Schema** for the `input` object (from Apify’s default actor build; **calls Apify**). |
| `POST` | `/{key}/run` | Same as `POST /run/{key}` (sync run + dataset). |
| `POST` | `/{key}/run-async` | Same as `POST /run-async/{key}`. |

**Examples (versioned):**

- `GET /v1/instagram/health`
- `GET /v1/metaAdLibrary/info`
- `GET /v1/instagram/input-json-schema` — all allowed `input` fields for that actor build
- `POST /v1/googleNews/run` with body `{ "input": { … } }`

**Input shapes:** the gateway does **not** validate `input`; it forwards the JSON to Apify. Any combination of fields the actor accepts will work. Use **`input-json-schema`** (or the actor’s Apify Store page) to discover properties and types.

In **Swagger UI** (`/docs`), each scraper appears as its **own tag** with these operations; `POST …/run` descriptions link to **`input-json-schema`** for the full input model.

---

### `GET /scrapers`

Lists all scrapers from `src/catalog.py` with metadata (no Apify call).

**Response** (`200`)

```json
{
  "scrapers": [
    {
      "key": "instagram",
      "title": "Instagram",
      "description": "...",
      "category": "demo",
      "actorId": "apify/instagram-scraper",
      "exampleInput": {},
      "apifyStoreUrl": "https://apify.com/apify/instagram-scraper"
    }
  ]
}
```

---

### `GET /scrapers/{scraper_key}`

Single scraper metadata.

**Path**

| Parameter      | Description                    |
|----------------|--------------------------------|
| `scraper_key`  | Same `key` as in the catalog   |

**Response** (`200`): one object like an element of `scrapers` above.

**Errors**

- `404` — unknown `scraper_key`

---

### `POST /run/{scraper_key}`

Starts the Apify actor with **`call()`**: waits until the run finishes, then reads the **default dataset** and returns all listed items (subject to Apify `list_items` behaviour for very large datasets).

**Path**

| Parameter      | Description   |
|----------------|---------------|
| `scraper_key`  | Catalog key   |

**Body**

```json
{
  "input": { }
}
```

`input` must match the actor’s input schema (see the actor page on Apify, linked from `apifyStoreUrl`).

**Response** (`200`)

```json
{
  "ok": true,
  "scraperKey": "instagram",
  "actorId": "apify/instagram-scraper",
  "runId": "<apify-run-id>",
  "status": "SUCCEEDED",
  "itemCount": 0,
  "items": []
}
```

**Errors** (same shape for all handled failures)

```json
{
  "ok": false,
  "scraperKey": "badKey",
  "error": {
    "code": "UNKNOWN_SCRAPER",
    "message": "Unknown scraper",
    "httpStatus": 404
  }
}
```

- `404` — unknown scraper (`UNKNOWN_SCRAPER`)
- `502` — Apify API error (`APIFY_ERROR`)
- `500` — unexpected failure (`INTERNAL_ERROR`)

**Note:** Long runs may hit HTTP timeouts on your host (e.g. Render). Prefer `POST /run-async/...` for heavy jobs.

---

### `POST /run-async/{scraper_key}`

Starts the actor with **`start()`** and returns immediately with run and default dataset ids.

**Status** `202 Accepted`

**Body**: same as `POST /run/{scraper_key}`.

**Response**

```json
{
  "ok": true,
  "scraperKey": "instagram",
  "actorId": "apify/instagram-scraper",
  "runId": "<apify-run-id>",
  "status": "READY",
  "defaultDatasetId": "<dataset-id>"
}
```

Poll Apify (API or console) for run status and dataset items, or add webhooks later.

---

## RapidAPI: per-scraper endpoints and usage billing

1. **Base URL** in RapidAPI = your gateway host (no path), e.g. `https://your-app.onrender.com`.
2. Add **one API product or one group of operations per scraper**, each with a **different path prefix**, e.g.  
   `POST https://…/v1/instagram/run`, `GET https://…/v1/instagram/health`, … vs `POST https://…/v1/metaAdLibrary/run`, …  
   (Legacy `POST /v1/run/{key}` still works if you prefer a single path pattern.)  
   RapidAPI will **meter and bill per operation** according to the plans you configure there.
3. **Body** for each: `{ "input": { … } }` — copy `exampleInput` from `GET /v1/scrapers` for that key.
4. **Apify token**: configure **only** on the server as `APIFY_TOKEN`. Subscribers never see it; they only use the **RapidAPI key**.

---

## Default catalog (Shop Intel)

| Key | Default actor | Notes |
|-----|---------------|--------|
| `metaAdLibrary` | `whoareyouanas/meta-ad-scraper` | Meta Ad Library search; browser-heavy. |
| `instagram` | `apify/instagram-scraper` | `directUrls`, `resultsLimit`, … |
| `whatsapp` | `curious_coder/whatsapp-scraper` | Often needs QR / `sessionStoreId` (see actor). |
| `googleNews` | `automation-lab/google-news-scraper` | `queries`, `maxArticles`, … |
| `amazonMarketplace` | `delicious_zebu/amazon-product-details-scraper` | `Params` (ASINs/URLs). |
| `googlePlaces` | `codingfrontend/google-maps-places-scraper` | `searchStringsArray`, `locationQuery`, … |

Override actors with `APIFY_ACTOR_*` env vars (see `src/catalog.py`). Exact `exampleInput`: **`GET /scrapers`**.

---

## Configuring scrapers

Edit **`src/catalog.py`**, tuple **`SCRAPERS`**:

- **`key`** — URL segment; use stable names for RapidAPI operations.
- **`actor_id`** — Apify actor ID, e.g. `your-user/your-actor`.
- **`title`**, **`description`**, **`category`**, **`example_input`**, **`apify_store_url`** — documentation only (shown in `/scrapers`).

After changes, redeploy (Render) or restart Uvicorn locally.

## RapidAPI mapping

1. Set API **base URL** to your gateway origin (no trailing slash).
2. For each scraper, add an operation, e.g. `POST /v1/run/instagram`.
3. Body template: `{ "input": { } }` — adjust per actor.
4. Optional: enable proxy verification and set `RAPIDAPI_PROXY_SECRET` on the server; configure RapidAPI to send `X-RapidAPI-Proxy-Secret`.

## Cost

Actor runs are billed by **Apify** (compute, proxies, etc.) according to your Apify plan. This gateway only forwards requests.
