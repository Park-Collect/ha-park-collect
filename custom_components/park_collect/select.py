"""Select entity: the parking lot used when a report names none."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ParkCollectConfigEntry
from .const import DOMAIN
from .coordinator import ParkingCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ParkCollectConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the select entity."""
    async_add_entities([ParkingLotSelect(entry)])


def device_info(entry: ParkCollectConfigEntry) -> DeviceInfo:
    """Group all entities of an account."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        entry_type=DeviceEntryType.SERVICE,
        manufacturer="Park Collect AG",
        name="Park & Collect",
    )


class ParkingLotSelect(CoordinatorEntity[ParkingCoordinator], SelectEntity, RestoreEntity):
    """Chooses the default parking lot; options come from the API."""

    _attr_has_entity_name = True
    _attr_translation_key = "parking_lot"

    def __init__(self, entry: ParkCollectConfigEntry) -> None:
        super().__init__(entry.runtime_data.parking)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_parking_lot"
        self._attr_device_info = device_info(entry)

    def _labels(self) -> dict[str, int]:
        return {
            f"{lot['name']} ({lot_id})": lot_id
            for lot_id, lot in self.coordinator.data.items()
        }

    @property
    def options(self) -> list[str]:
        return list(self._labels())

    @property
    def current_option(self) -> str | None:
        selected = self._entry.runtime_data.default_parking_id
        return next(
            (label for label, lot_id in self._labels().items() if lot_id == selected),
            None,
        )

    async def async_added_to_hass(self) -> None:
        """Restore the choice; a single parking lot is chosen automatically."""
        await super().async_added_to_hass()
        labels = self._labels()
        last = await self.async_get_last_state()
        if last is not None and last.state in labels:
            self._entry.runtime_data.default_parking_id = labels[last.state]
        elif len(labels) == 1:
            self._entry.runtime_data.default_parking_id = next(iter(labels.values()))

    async def async_select_option(self, option: str) -> None:
        """Change the default parking lot."""
        self._entry.runtime_data.default_parking_id = self._labels()[option]
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Forget a parking lot that no longer exists."""
        data = self._entry.runtime_data
        if data.default_parking_id not in self.coordinator.data:
            data.default_parking_id = None
        super()._handle_coordinator_update()
