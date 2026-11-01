"""Client for the Park & Collect report API (docs: REPORTS-API.md in PC-WebApp)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import API_BASE_URL

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
# POST /meldungen may take up to 60 seconds on the server side.
REPORT_TIMEOUT = aiohttp.ClientTimeout(total=75)
UPLOAD_TIMEOUT = aiohttp.ClientTimeout(total=60)

RETRIES = 3
RETRY_BASE_SECONDS = 2
RETRY_MAX_SECONDS = 60
RETRYABLE_STATUS = {409, 429, 500, 502, 503, 504}


class ParkCollectError(Exception):
    """A request to Park & Collect failed."""


class ParkCollectAuthError(ParkCollectError):
    """The API key is missing, wrong, or the account is blocked."""


class ParkCollectValidationError(ParkCollectError):
    """The API rejected the report; repeating it will not help."""


@dataclass(frozen=True)
class Photo:
    """A photo ready for upload."""

    content: bytes
    content_type: str
    taken_at: str


class ParkCollectClient:
    """Thin wrapper around the four endpoints of the report API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        base_url: str = API_BASE_URL,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def async_get_parking_lots(self) -> list[dict[str, Any]]:
        """Return all parking lots of the account."""
        data = await self._request("GET", "/parkplaetze")
        return data["parkplaetze"]

    async def async_get_report(self, report_id: int) -> dict[str, Any]:
        """Return the processing status of a report."""
        return await self._request("GET", f"/meldungen/{report_id}")

    async def async_submit_report(
        self,
        report: dict[str, Any],
        photos: list[Photo],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Upload the photos and create the report.

        Retries reuse the same upload IDs and body, so the API recognises a
        repeated request by its Idempotency-Key and never creates a duplicate.
        """
        uploaded = [
            {
                "upload_id": await self._async_upload(photo),
                "aufgenommen_am": photo.taken_at,
            }
            for photo in photos
        ]
        return await self._request(
            "POST",
            "/meldungen",
            json={**report, "fotos": uploaded},
            headers={"Idempotency-Key": idempotency_key},
            timeout=REPORT_TIMEOUT,
        )

    async def _async_upload(self, photo: Photo) -> str:
        created = await self._request(
            "POST", "/uploads", json={"content_type": photo.content_type}
        )
        try:
            async with self._session.put(
                created["upload_url"],
                data=photo.content,
                # The signed URL must not receive the API key.
                headers={"Content-Type": photo.content_type},
                timeout=UPLOAD_TIMEOUT,
            ) as response:
                if response.status >= 400:
                    raise ParkCollectError(f"Photo upload failed ({response.status})")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ParkCollectError("Photo upload failed") from err
        return created["upload_id"]

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: aiohttp.ClientTimeout = REQUEST_TIMEOUT,
    ) -> dict[str, Any]:
        request_headers = {"Authorization": f"Bearer {self._api_key}", **(headers or {})}
        last_error: ParkCollectError | None = None

        for attempt in range(RETRIES):
            if attempt:
                await asyncio.sleep(RETRY_BASE_SECONDS * 2 ** (attempt - 1))
            try:
                async with self._session.request(
                    method,
                    f"{self._base_url}{path}",
                    json=json,
                    headers=request_headers,
                    timeout=timeout,
                ) as response:
                    body = await response.json(content_type=None)
                    status = response.status
                    retry_after = response.headers.get("Retry-After")
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                last_error = ParkCollectError(f"Park & Collect not reachable: {err!r}")
                continue

            if status < 400:
                return body
            if status in (401, 403):
                raise ParkCollectAuthError(body.get("error", f"HTTP {status}"))

            message = _error_message(body, status)
            if status not in RETRYABLE_STATUS or _is_key_conflict(status, body):
                raise ParkCollectValidationError(message)

            last_error = ParkCollectError(message)
            if retry_after and retry_after.isdigit() and attempt < RETRIES - 1:
                await asyncio.sleep(min(int(retry_after), RETRY_MAX_SECONDS))

        raise last_error or ParkCollectError("Request failed")


def _is_key_conflict(status: int, body: dict[str, Any]) -> bool:
    """Tell 'same key, other content' from 'first request still running'."""
    return status == 409 and "anderem Inhalt" in str(body.get("error", ""))


def _error_message(body: dict[str, Any], status: int) -> str:
    if details := body.get("fehler"):
        return "; ".join(f"{item['feld']}: {item['meldung']}" for item in details)
    return str(body.get("error", f"HTTP {status}"))
