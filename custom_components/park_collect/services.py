"""The submit_report service."""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
import hashlib
import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .api import ParkCollectError, Photo
from .const import (
    DOMAIN,
    EVENT_REPORT_SUBMITTED,
    MAX_PHOTO_BYTES,
    MAX_PHOTOS,
    REASONS,
    SERVICE_SUBMIT_REPORT,
)

PHOTO_SCHEMA = vol.Any(
    cv.string,
    vol.Schema(
        {vol.Required("pfad"): cv.string, vol.Optional("aufgenommen_am"): cv.datetime}
    ),
)

SUBMIT_REPORT_SCHEMA = vol.Schema(
    {
        vol.Optional("parkplatz_id"): vol.Coerce(int),
        vol.Required("kennzeichen"): cv.string,
        vol.Required("beginn"): cv.datetime,
        vol.Optional("ende"): cv.datetime,
        vol.Optional("grund", default="privatparkplatz"): vol.In(REASONS),
        vol.Optional("vertragsstrafe"): vol.All(vol.Coerce(int), vol.Range(1, 70)),
        vol.Optional("abmahnen"): cv.boolean,
        vol.Optional("fahrzeug"): cv.string,
        vol.Optional("bemerkung"): cv.string,
        vol.Required("bilder"): vol.All(
            cv.ensure_list, vol.Length(min=1, max=MAX_PHOTOS), [PHOTO_SCHEMA]
        ),
        vol.Optional("vorgang_id"): vol.All(cv.string, vol.Length(min=1)),
    }
)


def _detect_content_type(content: bytes) -> str | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


def _iso(value: datetime, default_tz: tzinfo) -> str:
    """Return ISO 8601; naive values are local time of this Home Assistant."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=default_tz)
    return value.isoformat(timespec="seconds")


def _read_photo(path: str) -> tuple[bytes, float]:
    with open(path, "rb") as file:
        if os.fstat(file.fileno()).st_size > MAX_PHOTO_BYTES:
            raise ValueError("too_large")
        return file.read(), os.path.getmtime(path)


async def _async_load_photos(hass: HomeAssistant, photos: list[Any]) -> list[Photo]:
    loaded: list[Photo] = []
    for photo in photos:
        path, taken_at = (
            (photo, None)
            if isinstance(photo, str)
            else (photo["pfad"], photo.get("aufgenommen_am"))
        )
        if not hass.config.is_allowed_path(path):
            raise ServiceValidationError(
                f"{path} is not allowed; add its folder to allowlist_external_dirs"
            )
        try:
            content, mtime = await hass.async_add_executor_job(_read_photo, path)
        except ValueError as err:
            raise ServiceValidationError(f"{path} is larger than 10 MB") from err
        except OSError as err:
            raise ServiceValidationError(f"{path} cannot be read") from err

        content_type = _detect_content_type(content)
        if content_type is None:
            raise ServiceValidationError(f"{path} is not a JPEG or PNG")
        taken = taken_at or datetime.fromtimestamp(mtime, UTC)
        loaded.append(
            Photo(content, content_type, _iso(taken, dt_util.DEFAULT_TIME_ZONE))
        )
    return loaded


def _idempotency_key(call: ServiceCall, parking_id: int) -> str:
    """Build a key that stays the same when this parking event is sent again."""
    source = call.data.get("vorgang_id") or (
        f"{parking_id}|{call.data['kennzeichen'].upper()}|"
        f"{call.data['beginn'].isoformat()}"
    )
    return f"ha-{hashlib.sha256(source.encode()).hexdigest()[:40]}"


def _loaded_entry(hass: HomeAssistant) -> ConfigEntry:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry
    raise ServiceValidationError("Park & Collect is not set up")


def _parking_id(call: ServiceCall, entry: ConfigEntry) -> int:
    lots = entry.runtime_data.parking.data
    parking_id = call.data.get("parkplatz_id") or entry.runtime_data.default_parking_id
    if parking_id is None:
        raise ServiceValidationError(
            "Choose a parking lot: set parkplatz_id or the select entity"
        )
    if parking_id not in lots:
        raise ServiceValidationError(f"Parking lot {parking_id} is not in this account")
    return parking_id


async def async_submit_report(call: ServiceCall) -> ServiceResponse:
    """Send a report that a person has reviewed in Home Assistant."""
    hass = call.hass
    entry = _loaded_entry(hass)
    data = entry.runtime_data
    parking_id = _parking_id(call, entry)
    key = _idempotency_key(call, parking_id)

    if (known := data.store.reports.get(key)) is not None:
        return {**known, "wiederholt": True}

    photos = await _async_load_photos(hass, call.data["bilder"])
    default_tz = dt_util.DEFAULT_TIME_ZONE
    report: dict[str, Any] = {
        "parkplatz_id": parking_id,
        "kennzeichen": call.data["kennzeichen"],
        "beginn": _iso(call.data["beginn"], default_tz),
        "grund": call.data["grund"],
    }
    if "ende" in call.data:
        report["ende"] = _iso(call.data["ende"], default_tz)
    for name in ("vertragsstrafe", "abmahnen", "fahrzeug", "bemerkung"):
        if name in call.data:
            report[name] = call.data[name]

    try:
        result = await data.client.async_submit_report(report, photos, key)
    except ParkCollectError as err:
        raise HomeAssistantError(f"Report was not accepted: {err}") from err

    await data.store.async_remember(key, result)
    hass.bus.async_fire(EVENT_REPORT_SUBMITTED, result)
    await data.report.async_request_refresh()
    return result


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's service."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_SUBMIT_REPORT,
        async_submit_report,
        schema=SUBMIT_REPORT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
