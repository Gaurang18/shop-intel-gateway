#!/usr/bin/env python3
"""Create this repo as a Render web service via https://api.render.com/v1/services.

Requires:
  - RENDER_API_KEY (Dashboard → Account Settings → API Keys)
  - RENDER_OWNER_ID (team/user id, e.g. from GET /v1/owners)
  - APIFY_TOKEN in .env (project root) or in the environment

Render may return HTTP 402 until a payment method is on file for the workspace.

envSpecificDetails must be a flat object with buildCommand and startCommand
(not nested under nativeEnvironmentDetails).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path: Path, *, override: bool = False) -> None:
    """Set os.environ from KEY=value lines (no python-dotenv required)."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, rest = line.partition("=")
        key = key.strip()
        val = rest.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = val


def main() -> int:
    # Prefer values from project .env for this one-shot script.
    load_env_file(ROOT / ".env", override=True)
    render_key = os.environ.get("RENDER_API_KEY")
    owner_id = os.environ.get("RENDER_OWNER_ID")
    apify = os.environ.get("APIFY_TOKEN")
    if not render_key or not owner_id:
        print("Set RENDER_API_KEY and RENDER_OWNER_ID.", file=sys.stderr)
        return 1
    if not apify:
        print("Set APIFY_TOKEN in .env or the environment.", file=sys.stderr)
        return 1

    repo = os.environ.get("RENDER_REPO", "https://github.com/Gaurang18/shop-intel-gateway")
    branch = os.environ.get("RENDER_BRANCH", "main")
    name = os.environ.get("RENDER_SERVICE_NAME", "shop-intel-gateway")

    body = {
        "type": "web_service",
        "name": name,
        "ownerId": owner_id,
        "repo": repo,
        "branch": branch,
        "autoDeploy": "yes",
        "envVars": [{"key": "APIFY_TOKEN", "value": apify}],
        "serviceDetails": {
            "runtime": "python",
            "region": os.environ.get("RENDER_REGION", "oregon"),
            "healthCheckPath": "/health",
            "envSpecificDetails": {
                "buildCommand": "pip install -r requirements.txt",
                "startCommand": "uvicorn src.main:app --host 0.0.0.0 --port $PORT",
            },
        },
    }

    req = urllib.request.Request(
        "https://api.render.com/v1/services",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {render_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            print(resp.status)
            print(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(e.code, file=sys.stderr)
        print(body, file=sys.stderr)
        if e.code == 402:
            print(
                "\nRender returned 402: add a payment method for this workspace, then re-run:\n"
                "  https://dashboard.render.com/billing\n"
                "Alternatively create the service from the dashboard (New → Web Service)\n"
                "or connect this repo via Blueprint using render.yaml in the repo root.\n",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
