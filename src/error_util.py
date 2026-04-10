"""Normalize HTTP errors for a consistent JSON body."""

from __future__ import annotations

from typing import Any


def scraper_key_from_path(path: str) -> str | None:
    """Extract catalog key from `/run/{key}` or `/v1/run/{key}` (and run-async)."""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[-2] in ("run", "run-async"):
        return parts[-1]
    if len(parts) >= 3 and parts[-3] == "v1" and parts[-2] in ("run", "run-async"):
        return parts[-1]
    return None


def status_to_default_code(status: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        422: "VALIDATION_ERROR",
        502: "APIFY_ERROR",
        503: "SERVICE_UNAVAILABLE",
        500: "INTERNAL_ERROR",
    }.get(status, "ERROR")


def gateway_error_payload(status: int, detail: Any, path: str) -> dict[str, Any]:
    scraper_key: str | None = None
    code: str
    message: str

    if isinstance(detail, dict):
        code = str(detail.get("code") or status_to_default_code(status))
        message = str(detail.get("message") or detail.get("error") or code)
        scraper_key = detail.get("key")
        if scraper_key is not None:
            scraper_key = str(scraper_key)
    else:
        code = status_to_default_code(status)
        message = str(detail)

    if scraper_key is None:
        scraper_key = scraper_key_from_path(path)

    return {
        "ok": False,
        "scraperKey": scraper_key,
        "error": {"code": code, "message": message, "httpStatus": status},
    }
