"""The Park & Collect integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .api import ParkCollectClient
from .const import DOMAIN, STATUS_UPDATE_INTERVAL
from .coordinator import STORAGE_VERSION, ParkingCoordinator, ReportCoordinator, ReportStore
from .services import async_setup_services

PLATFORMS = [Platform.SELECT, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class ParkCollectData:
    """Runtime objects of a config entry."""

    client: ParkCollectClient
    parking: ParkingCoordinator
    report: ReportCoordinator
    store: ReportStore
    default_parking_id: int | None = None


type ParkCollectConfigEntry = ConfigEntry[ParkCollectData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the service once, independent of config entries."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ParkCollectConfigEntry) -> bool:
    """Set up Park & Collect from a config entry."""
    client = ParkCollectClient(async_get_clientsession(hass), entry.data[CONF_API_KEY])

    store = ReportStore(Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"))
    await store.async_load()

    parking = ParkingCoordinator(hass, entry, client)
    report = ReportCoordinator(hass, entry, client, store, STATUS_UPDATE_INTERVAL)
    await parking.async_config_entry_first_refresh()
    await report.async_config_entry_first_refresh()

    entry.runtime_data = ParkCollectData(client, parking, report, store)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ParkCollectConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
