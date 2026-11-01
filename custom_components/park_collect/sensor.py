"""Sensor: processing status of the most recent report."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ParkCollectConfigEntry
from .coordinator import ReportCoordinator
from .select import device_info

STATUSES = [
    "offen",
    "halterermittlung_laeuft",
    "halter_ermittelt",
    "erstschreiben_versendet",
    "abmahnung_versendet",
    "bezahlt",
    "abgeschlossen",
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParkCollectConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor."""
    async_add_entities([LastReportSensor(entry)])


class LastReportSensor(CoordinatorEntity[ReportCoordinator], SensorEntity):
    """Shows where the most recent report stands."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_report"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES

    def __init__(self, entry: ParkCollectConfigEntry) -> None:
        super().__init__(entry.runtime_data.report)
        self._attr_unique_id = f"{entry.entry_id}_last_report"
        self._attr_device_info = device_info(entry)

    @property
    def native_value(self) -> str | None:
        report = self.coordinator.data
        return report["status"] if report else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        report = self.coordinator.data
        if not report:
            return None
        return {
            "id": report["id"],
            "aktenzeichen": report["aktenzeichen"],
            "aktualisiert_am": report.get("aktualisiert_am"),
        }
