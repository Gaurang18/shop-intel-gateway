# Shop Intel Gateway (Python)

HTTP API on **FastAPI** that runs your **Apify actors** and returns rows from each run’s **default dataset**.  
No application database—Apify stores runs and data.

---

### Security warning

**Do not put Apify API tokens in git, in the README, or in client-side code.**  
If a token was ever shared in chat or committed, **revoke it** in [Apify → Integrations](https://console.apify.com/account/integrations) and create a new one.

This repo only reads **`APIFY_TOKEN`** from the environment (see `.env.example`).

---

## Features

- **Six Shop Intel scrapers** in `src/catalog.py` (Meta Ads, Instagram, WhatsApp, Google News, Amazon, Google Places); actor IDs overridable via env.
- **`/v1/...` routes** — same API as unversioned paths; use **`/v1`** as the RapidAPI-facing base for stable versioning.
- **Stable JSON** — successful runs: `ok`, `scraperKey`, `actorId`, `runId`, `status`, `itemCount`, `items`. Errors: `ok: false`, `error.code`, `error.message`.
- **OpenAPI** at `/docs`, `/redoc`, `/openapi.json`.
- **Extended docs** in [`docs/API.md`](docs/API.md).
- **RapidAPI provider guide** (scrapers, endpoints, params, examples): [`docs/RAPIDAPI.md`](docs/RAPIDAPI.md).
- **Tests** with mocked Apify (`pytest`) plus **optional live tests** against Apify.
- **`scripts/verify_scrapers.py`** — runs all catalog scrapers end-to-end (uses real quota).

## Quick start

```bash
cd shop-intel-gateway
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # edit .env — set APIFY_TOKEN only; never commit .env
export $(grep -v '^#' .env | xargs)   # or use direnv / your shell
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Open <http://127.0.0.1:8000/docs>.

## Endpoints (summary)

Each path below is also available under **`/v1`** (e.g. `GET /v1/scrapers`, `POST /v1/run/instagram`). Prefer **`/v1`** for new RapidAPI operations.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Service info, doc links, **RapidAPI** hints (`rapidApi` object) |
| GET | `/health` | Health (no Apify) |
| GET | `/scrapers` | List configured scrapers + `exampleInput` |
| GET | `/scrapers/{key}` | One scraper metadata |
| POST | `/run/{key}` | `call()` — wait and return dataset items |
| POST | `/run-async/{key}` | `start()` — return `runId` + `defaultDatasetId` (202) |

Optional auth: if **`RAPIDAPI_PROXY_SECRET`** is set, all **API** routes (including `/v1/...`) require header **`X-RapidAPI-Proxy-Secret`**. **`/`** and **`/health`** stay public.

Full reference: [`docs/API.md`](docs/API.md). **RapidAPI:** [`docs/RAPIDAPI.md`](docs/RAPIDAPI.md).

## RapidAPI: different scrapers, per-usage pricing, one Apify key

- **Per scraper → separate RapidAPI endpoint** — In the RapidAPI hub, add one operation per scraper with a **distinct URL**, e.g. `POST …/v1/run/instagram`, `POST …/v1/run/metaAdLibrary`. RapidAPI meters **each operation** separately, so you can attach **different usage plans / prices** per scraper.
- **One shared `APIFY_TOKEN` on the server** — The gateway uses a **single** Apify API token (your “shared key”) for all actors. It lives only in **Render/env** — **never** in RapidAPI consumer headers. Subscribers authenticate with **RapidAPI’s key** only.
- **Proxy secret (optional)** — Set `RAPIDAPI_PROXY_SECRET` on the server and enable RapidAPI proxy verification so only traffic from RapidAPI can hit your billable routes.

## Scrapers (catalog)

Defined in **`src/catalog.py`**. Defaults point at public Store actors; set **`APIFY_ACTOR_*`** env vars to use your own.

| Key | Role | Default actor |
|-----|------|----------------|
| `metaAdLibrary` | Meta Ad Library | `whoareyouanas/meta-ad-scraper` |
| `instagram` | Instagram | `apify/instagram-scraper` |
| `whatsapp` | WhatsApp business lookup | `curious_coder/whatsapp-scraper` (QR / session — see docs) |
| `googleNews` | Google News | `automation-lab/google-news-scraper` |
| `amazonMarketplace` | Amazon product details | `delicious_zebu/amazon-product-details-scraper` |
| `googlePlaces` | Google Maps / Places | `codingfrontend/google-maps-places-scraper` |

Use **`GET /scrapers`** (or **`GET /v1/scrapers`**) for `exampleInput` per key. **RapidAPI reference:** [`docs/RAPIDAPI.md`](docs/RAPIDAPI.md).

**Automated live tests** (`pytest tests/test_live_scrapers.py`, `verify_scrapers.py`) run all except **`whatsapp`**. To try WhatsApp in verify: `VERIFY_WHATSAPP=1 python scripts/verify_scrapers.py`.

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
```

Unit tests mock Apify. **Live tests** (`tests/test_live_scrapers.py`) are **skipped** unless `APIFY_TOKEN` is set to a **real** token (not `test-apify-token`). They call Apify and can take several minutes.

```bash
export APIFY_TOKEN='apify_api_...'   # real token; never commit
pytest tests/test_live_scrapers.py -v --tb=short
```

### Verify all scrapers (script)

Same as live tests but prints one block per scraper (still bills Apify like normal runs):

```bash
export APIFY_TOKEN='apify_api_...'
python scripts/verify_scrapers.py
```

### Optional curl smoke (server must be running)

```bash
export APIFY_TOKEN='apify_api_...'
uvicorn src.main:app --host 0.0.0.0 --port 8000   # other terminal
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/scrapers | head -c 600
curl -s -X POST http://127.0.0.1:8000/v1/run/googleNews -H 'Content-Type: application/json' -d '{"input":{"queries":["ai"],"maxArticles":3}}'
```

## Deploy on Render

**Do not commit `APIFY_TOKEN` in git.** The app loads optional `shop-intel-gateway/.env` **locally only** (file is gitignored). On Render, the platform injects environment variables — put the token there.

### 1. Push this folder to GitHub

```bash
cd shop-intel-gateway
git init
git add .
git status   # confirm .env is NOT listed (gitignored)
git commit -m "Shop Intel gateway"
# Create an empty repo on GitHub, then:
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git branch -M main
git push -u origin main
```

### 2. Create a Render Web Service

1. [Render Dashboard](https://dashboard.render.com/) → **New** → **Web Service** → connect the GitHub repo.
2. **Root directory**: leave empty if the repo root *is* `shop-intel-gateway`; if the repo contains a parent folder, set root to `shop-intel-gateway`.
3. **Runtime**: Python 3 (matches `runtime.txt`).
4. **Build command**: `pip install -r requirements.txt`
5. **Start command**: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`

### 3. Environment variables (required)

In the service → **Environment** → add:

| Key | Value |
|-----|--------|
| `APIFY_TOKEN` | Your Apify token (same as in local `.env`) |

Optional: `RAPIDAPI_PROXY_SECRET` if you use RapidAPI proxy verification.

**Save** and deploy. When the deploy is live, open `https://YOUR-SERVICE.onrender.com/health` and `https://YOUR-SERVICE.onrender.com/docs`.

`render.yaml` can be used for a **Blueprint** instead of manual settings; secrets still belong in the dashboard, not in the file.

## RapidAPI (checklist)

1. **Base URL** = your gateway origin only, e.g. `https://your-app.onrender.com` (no trailing slash).
2. **Add one operation per scraper** with the full path, e.g. `POST /v1/run/instagram`, `POST /v1/run/googlePlaces`.
3. **Request body** = `{ "input": { … } }` — use `exampleInput` from `GET /v1/scrapers` as the template for each operation.
4. **Pricing** = configure **per endpoint** in RapidAPI (usage / quota); your server does not implement billing.
5. Optionally set **`RAPIDAPI_PROXY_SECRET`** on Render and send **`X-RapidAPI-Proxy-Secret`** from RapidAPI.

## Project layout

```
shop-intel-gateway/
  docs/API.md           # Human-readable API reference
  docs/RAPIDAPI.md      # RapidAPI: endpoints, params, scrapers, examples
  scripts/
    verify_scrapers.py  # End-to-end check of every catalog scraper
  src/
    catalog.py          # Scraper registry (edit this for Shop Intel)
    main.py             # FastAPI app
    schemas.py          # Pydantic models
  tests/                # Pytest + mocks
  requirements.txt
  requirements-dev.txt
  runtime.txt
  render.yaml
  .env.example
```

## License

Use and modify for your own deployment; actor usage remains subject to Apify and third-party sites’ terms.
