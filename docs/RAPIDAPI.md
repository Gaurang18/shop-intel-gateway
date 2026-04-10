# RapidAPI integration guide — Shop Intel Gateway

This document is for **publishing and consuming** the Shop Intel Gateway through [RapidAPI](https://rapidapi.com/). It lists **every scraper**, **every HTTP endpoint**, **parameters**, **headers**, **response shapes**, and **copy-paste examples**.

Your deployed API base looks like: `https://<your-service>.onrender.com` (example). In RapidAPI you enter **only that origin** as the API base URL — **no trailing slash**.

---

## 1. How this maps to RapidAPI

| Concept | How it works |
|--------|----------------|
| **One scraper** | One **catalog key** (e.g. `instagram`) → its **own path prefix**, e.g. `POST /v1/instagram/run`, `GET /v1/instagram/health` (legacy `POST /v1/run/instagram` still works). |
| **Per-usage billing** | In RapidAPI, create **one API operation per path**. RapidAPI counts **one billable request per HTTP call** to that operation (according to the plans you configure). |
| **Apify** | The server uses **`APIFY_TOKEN`** to call Apify. Subscribers use **only** the RapidAPI key; they **never** receive your Apify token. |
| **Versioned URLs** | Prefer paths under **`/v1/`** for all new RapidAPI operations. The same routes exist **without** `/v1` for backward compatibility. |

---

## 2. Authentication and headers

### 2.1 RapidAPI → subscriber

Subscribers call RapidAPI; RapidAPI forwards to your backend. Typical headers RapidAPI can send (depending on your API definition):

| Header | Required | Description |
|--------|----------|-------------|
| `X-RapidAPI-Key` | Yes (on RapidAPI) | Subscriber’s RapidAPI key. You do **not** validate this in this gateway unless you add custom logic. |
| `X-RapidAPI-Host` | Set by RapidAPI | When using RapidAPI’s proxy, identifies the API. |

This gateway **does not** require `X-RapidAPI-Key` on the server by default (RapidAPI sits in front). If you expose the **raw** Render URL publicly, protect it (see proxy secret below).

### 2.2 Optional: verify traffic is from RapidAPI

If you set environment variable **`RAPIDAPI_PROXY_SECRET`** on the server, then **every route in the table below except `GET /` and `GET /health`** requires (including **`GET /v1/{key}/health`** per scraper):

| Header | Value |
|--------|--------|
| `X-RapidAPI-Proxy-Secret` | Exact match of `RAPIDAPI_PROXY_SECRET` |

Configure the same secret in RapidAPI **proxy verification** so only RapidAPI-originated requests hit your billable routes.

### 2.3 Content type

All POST bodies are JSON:

| Header | Value |
|--------|--------|
| `Content-Type` | `application/json` |

---

## 3. Endpoints overview

Paths are listed **with `/v1`** (recommended). The same path **without** `/v1` also works (e.g. `/scrapers` and `/v1/scrapers`).

| Method | Path | Auth (if `RAPIDAPI_PROXY_SECRET` set) | Description |
|--------|------|----------------------------------------|-------------|
| GET | `/` | No | Service name, version, doc links, RapidAPI hints. |
| GET | `/health` | No | Liveness; does **not** call Apify. |
| GET | `/v1/scrapers` | Yes | List all scrapers + metadata + `exampleInput`. |
| GET | `/v1/scrapers/{scraper_key}` | Yes | One scraper by key (same JSON as `GET /v1/{key}/info`). |
| GET | `/v1/{scraper_key}/health` | Yes | Per-scraper liveness; does **not** call Apify. |
| GET | `/v1/{scraper_key}/info` | Yes | Metadata for that scraper only. |
| GET | `/v1/{scraper_key}/input-json-schema` | Yes | **JSON Schema** for `input` (from Apify default build; calls Apify). |
| POST | `/v1/{scraper_key}/run` | Yes | Run actor to completion; return **default dataset** rows. |
| POST | `/v1/{scraper_key}/run-async` | Yes | Start actor only; return `runId` and `defaultDatasetId` (HTTP **202**). |
| POST | `/v1/run/{scraper_key}` | Yes | **Legacy** sync run (same as `POST /v1/{key}/run`). |
| POST | `/v1/run-async/{scraper_key}` | Yes | **Legacy** async start (same as `POST /v1/{key}/run-async`). |

**Path parameter**

| Name | Location | Description |
|------|----------|-------------|
| `scraper_key` | Path | Catalog key: `metaAdLibrary`, `instagram`, `whatsapp`, `googleNews`, `amazonMarketplace`, `googlePlaces` (see `src/catalog.py`). |

---

## 3b. Run `input`: all Apify permutations

- The gateway sends `body.input` to Apify as **`runInput` unchanged**. It does **not** check required fields or enums; **every valid combination** the actor supports can be sent in one `POST …/run`.
- To see **allowed properties, types, and descriptions** for the deployed actor version, call **`GET /v1/{scraper_key}/input-json-schema`** (returns Apify’s JSON Schema for the default build). Your catalog `exampleInput` and Swagger **examples** are hints only.
- You do **not** need separate HTTP routes per input “mode” unless you want different RapidAPI operations for billing/UX—the same `POST …/run` already accepts all modes the actor allows.

---

## 4. Request body (all `POST /v1/.../run`, `POST /v1/.../run-async`, and legacy `POST /v1/run/...` / `POST /v1/run-async/...`)

Single JSON object:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `input` | object | No* | Actor input as Apify expects (`runInput`). Empty `{}` is allowed where the actor allows it. |

\* Some actors require fields inside `input` (e.g. `startUrls`). Use `GET /v1/scrapers` to see **`exampleInput`** per scraper.

**Example (generic):**

```json
{
  "input": {
    "startUrls": [{ "url": "https://example.com/" }]
  }
}
```

---

## 5. Success responses

### 5.1 `POST /v1/run/{scraper_key}` — HTTP 200

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Always `true`. |
| `scraperKey` | string | Same as `{scraper_key}` in the URL. |
| `actorId` | string | Apify actor ID that executed. |
| `runId` | string | Apify run id. |
| `status` | string | Final run status (e.g. `SUCCEEDED`). |
| `itemCount` | integer | Number of rows; equals `items.length`. |
| `items` | array | Objects from the run’s **default dataset**. |

**Example:**

```json
{
  "ok": true,
  "scraperKey": "instagram",
  "actorId": "apify/instagram-scraper",
  "runId": "abc123",
  "status": "SUCCEEDED",
  "itemCount": 1,
  "items": [{ "message": "Hello world!" }]
}
```

### 5.2 `POST /v1/run-async/{scraper_key}` — HTTP 202

| Field | Type | Description |
|-------|------|-------------|
| `ok` | boolean | Always `true`. |
| `scraperKey` | string | Path key. |
| `actorId` | string | Apify actor ID. |
| `runId` | string | Use to poll run status in Apify. |
| `status` | string | Early status (e.g. `READY`). |
| `defaultDatasetId` | string | Dataset id when the run finishes. |

**Example:**

```json
{
  "ok": true,
  "scraperKey": "instagram",
  "actorId": "apify/instagram-scraper",
  "runId": "xyz789",
  "status": "READY",
  "defaultDatasetId": "datasetIdHere"
}
```

### 5.3 `GET /v1/scrapers` — HTTP 200

```json
{
  "scrapers": [
    {
      "key": "instagram",
      "title": "Instagram",
      "description": "…",
      "category": "demo",
      "actorId": "apify/instagram-scraper",
      "exampleInput": {},
      "apifyStoreUrl": "https://apify.com/apify/instagram-scraper"
    }
  ]
}
```

### 5.4 `GET /v1/scrapers/{scraper_key}` — HTTP 200

One object of the same shape as a single element of `scrapers[]` above.

### 5.5 `GET /` — HTTP 200

Includes `service`, `version`, `docs`, and `rapidApi` (billing / token hints).

### 5.6 `GET /health` — HTTP 200

```json
{ "ok": true }
```

---

## 6. Error responses

All handled errors use this shape (HTTP status in the response line; body includes `error.httpStatus` matching it):

```json
{
  "ok": false,
  "scraperKey": "optional-or-null",
  "error": {
    "code": "UNKNOWN_SCRAPER",
    "message": "Unknown scraper",
    "httpStatus": 404
  }
}
```

| HTTP | Typical `error.code` | Meaning |
|------|----------------------|---------|
| 401 | `UNAUTHORIZED` | Missing/wrong `X-RapidAPI-Proxy-Secret` when that env is set. |
| 404 | `UNKNOWN_SCRAPER` | `scraper_key` not in the catalog. |
| 422 | `VALIDATION_ERROR` | JSON body invalid (e.g. malformed JSON). |
| 502 | `APIFY_ERROR` | Apify API rejected or failed the run. |
| 500 | `INTERNAL_ERROR` | Unexpected server error. |

---

## 7. Scrapers (Shop Intel catalog)

Defined in **`src/catalog.py`**. Each **key** is one RapidAPI operation path: `POST /v1/run/{key}`.

**Override Apify actors** (same keys, your own `username/actor-name`) with environment variables on the server:

| Variable | Default actor |
|----------|----------------|
| `APIFY_ACTOR_META_AD_LIBRARY` | `whoareyouanas/meta-ad-scraper` |
| `APIFY_ACTOR_INSTAGRAM` | `apify/instagram-scraper` |
| `APIFY_ACTOR_WHATSAPP` | `curious_coder/whatsapp-scraper` |
| `APIFY_ACTOR_GOOGLE_NEWS` | `automation-lab/google-news-scraper` |
| `APIFY_ACTOR_AMAZON` | `delicious_zebu/amazon-product-details-scraper` |
| `APIFY_ACTOR_GOOGLE_PLACES` | `codingfrontend/google-maps-places-scraper` |

| Key (`scraper_key`) | Title | Category | Default `actorId` | Automated test |
|---------------------|-------|----------|-------------------|----------------|
| `metaAdLibrary` | Meta Ad Library | ads | `whoareyouanas/meta-ad-scraper` | Yes |
| `instagram` | Instagram | social | `apify/instagram-scraper` | Yes |
| `whatsapp` | WhatsApp (profiles) | social | `curious_coder/whatsapp-scraper` | **No** (QR / Live view) |
| `googleNews` | Google News | news | `automation-lab/google-news-scraper` | Yes |
| `amazonMarketplace` | Amazon product details | ecommerce | `delicious_zebu/amazon-product-details-scraper` | Yes |
| `googlePlaces` | Google Maps / Places | local | `codingfrontend/google-maps-places-scraper` | Yes |

Full options for each actor: **`apifyStoreUrl`** from `GET /v1/scrapers`, or:

| Key | Apify store |
|-----|-------------|
| `metaAdLibrary` | [whoareyouanas/meta-ad-scraper](https://apify.com/whoareyouanas/meta-ad-scraper) |
| `instagram` | [apify/instagram-scraper](https://apify.com/apify/instagram-scraper) |
| `whatsapp` | [curious_coder/whatsapp-scraper](https://apify.com/curious_coder/whatsapp-scraper) |
| `googleNews` | [automation-lab/google-news-scraper](https://apify.com/automation-lab/google-news-scraper) |
| `amazonMarketplace` | [delicious_zebu/amazon-product-details-scraper](https://apify.com/delicious_zebu/amazon-product-details-scraper) |
| `googlePlaces` | [codingfrontend/google-maps-places-scraper](https://apify.com/codingfrontend/google-maps-places-scraper) |

---

## 8. Per-scraper: paths, options, examples

Use **one RapidAPI endpoint per key**. Method: **POST**. Body: `{ "input": { … } }`.

**cURL template** (add `X-RapidAPI-Proxy-Secret` if you use proxy verification):

```bash
curl -sS -X POST "https://YOUR_HOST/v1/run/<KEY>" \
  -H "Content-Type: application/json" \
  -d @body.json
```

---

### 8.1 `metaAdLibrary`

| Path | `POST /v1/run/metaAdLibrary` |
|------|---------------------------------|
| **Notes** | Browser-heavy; use a narrow `searchQuery`. Optional `targetUrl` (Ad Library URL) overrides other fields per actor docs. |

```json
{
  "input": {
    "searchQuery": "apify",
    "country": "US",
    "activeStatus": "active",
    "adType": "all",
    "mediaType": "all",
    "maxConcurrency": 1
  }
}
```

---

### 8.2 `instagram`

| Path | `POST /v1/run/instagram` |
|------|---------------------------|
| **Notes** | `directUrls` = profile/post URLs; `resultsLimit` caps items. |

```json
{
  "input": {
    "directUrls": ["https://www.instagram.com/apifytech/"],
    "resultsLimit": 3,
    "addParentData": false
  }
}
```

---

### 8.3 `whatsapp`

| Path | `POST /v1/run/whatsapp` |
|------|-------------------------|
| **Notes** | **Not run in automated tests.** First run: open Apify **Live view**, scan QR (WhatsApp → Linked devices). Reuse **`sessionStoreId`** in later runs. Optional **`proxy`** object recommended on the actor (see Apify README). |

```json
{
  "input": {
    "numbers": ["8976859807"],
    "sessionStoreId": "whatsapp-session-1"
  }
}
```

To include `whatsapp` in `scripts/verify_scrapers.py`: `VERIFY_WHATSAPP=1 python scripts/verify_scrapers.py`.

---

### 8.4 `googleNews`

| Path | `POST /v1/run/googleNews` |
|------|---------------------------|
| **Notes** | `queries` = string array; `maxArticles` per query (see actor for countries/topics). |

```json
{
  "input": {
    "queries": ["artificial intelligence"],
    "maxArticles": 5
  }
}
```

---

### 8.5 `amazonMarketplace`

| Path | `POST /v1/run/amazonMarketplace` |
|------|-----------------------------------|
| **Notes** | `Params` = ASINs and/or Amazon product URLs (see actor). |

```json
{
  "input": {
    "Params": ["B00091S3K4"]
  }
}
```

---

### 8.6 `googlePlaces`

| Path | `POST /v1/run/googlePlaces` |
|------|------------------------------|
| **Notes** | `searchStringsArray` + `locationQuery`; tune `maxCrawledPlacesPerSearch`, reviews, filters on Apify. |

```json
{
  "input": {
    "searchStringsArray": ["coffee shop"],
    "locationQuery": "San Francisco, USA",
    "maxCrawledPlacesPerSearch": 3,
    "language": "en"
  }
}
```

---

## 9. Async variant (same `input`, different path)

For any `scraper_key`, you can expose a **second** RapidAPI operation:

`POST /v1/run-async/{scraper_key}`

Same JSON body as sync. Response is **202** with `runId` / `defaultDatasetId`; subscribers poll Apify or you add webhooks later.

**Example:**

```bash
curl -sS -X POST "https://YOUR_HOST/v1/run-async/googleNews" \
  -H "Content-Type: application/json" \
  -d '{"input":{"queries":["tech"],"maxArticles":3}}'
```

---

## 10. Adding a new scraper (then a new RapidAPI endpoint)

1. Add a row to **`SCRAPERS`** in `src/catalog.py` (`key`, `actor_id`, `example_input`, …).
2. Redeploy the gateway.
3. In RapidAPI, **add a new operation**: `POST /v1/run/<newKey>` (and optionally `POST /v1/run-async/<newKey>`).
4. Set the request body template to `{ "input": <paste exampleInput from GET /v1/scrapers> }`.
5. Set **pricing / quota** for that operation independently.

---

## 11. RapidAPI Hub checklist

1. **Create API** → set **Base URL** = `https://YOUR_HOST` (no trailing slash).
2. Add operations with **full path** including `/v1`, e.g. `POST /v1/run/instagram`, `POST /v1/run/metaAdLibrary`, …
3. Define **body** as JSON: `{ "input": { … } }`.
4. **Test** from RapidAPI’s console; if using proxy verification, configure **`X-RapidAPI-Proxy-Secret`** on both sides.
5. **Publish** and attach **usage-based** plans per endpoint as needed.

---

## 12. Related

- Machine-readable OpenAPI: `GET /openapi.json` or **`/docs`** on your deployed host.
- General API reference: [`docs/API.md`](API.md).
- Project overview: [`README.md`](../README.md).

---

*Gateway version at time of writing: **1.4.0** (see `GET /` → `version`).*
