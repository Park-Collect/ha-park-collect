"""Data handling for the Park & Collect integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ParkCollectAuthError, ParkCollectClient, ParkCollectError
from .const import DOMAIN, PARKING_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
MAX_REMEMBERED_REPORTS = 200


class ParkingCoordinator(DataUpdateCoordinator[dict[int, dict[str, Any]]]):
    """Keeps the parking lots of the account, keyed by ID."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ParkCollectClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_parking",
            update_interval=PARKING_UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[int, dict[str, Any]]:
        try:
            lots = await self.client.async_get_parking_lots()
        except ParkCollectAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ParkCollectError as err:
            raise UpdateFailed(str(err)) from err
        return {lot["id"]: lot for lot in lots}


class ReportCoordinator(DataUpdateCoordinator[dict[str, Any] | None]):
    """Follows the status of the most recent report."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ParkCollectClient,
        store: ReportStore,
        interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_report",
            update_interval=interval,
        )
        self.client = client
        self.store = store

    async def _async_update_data(self) -> dict[str, Any] | None:
        last = self.store.last_report
        if last is None:
            return None
        try:
            return await self.client.async_get_report(last["id"])
        except ParkCollectAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ParkCollectError as err:
            raise UpdateFailed(str(err)) from err


@dataclass
class ReportStore:
    """Remembers submitted reports across restarts.

    The API treats the same Idempotency-Key with new upload IDs as a conflict.
    Knowing the key here lets a repeated service call return the earlier report
    without uploading the photos again.
    """

    store: Store[dict[str, Any]]
    reports: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_report: dict[str, Any] | None = None

    async def async_load(self) -> None:
        """Load the remembered reports."""
        data = await self.store.async_load() or {}
        self.reports = data.get("reports", {})
        self.last_report = data.get("last_report")

    async def async_remember(self, key: str, report: dict[str, Any]) -> None:
        """Remember a successfully submitted report."""
        self.reports[key] = report
        self.last_report = report
        for oldest in list(self.reports)[: -MAX_REMEMBERED_REPORTS]:
            del self.reports[oldest]
        await self.store.async_save(
            {"reports": self.reports, "last_report": self.last_report}
        )
