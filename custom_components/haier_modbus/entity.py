"""Gemeinsame Entity-Basis mit Geräteinfo."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import HaierModbusCoordinator


class HaierModbusEntity(CoordinatorEntity[HaierModbusCoordinator]):
    """Basisklasse – bündelt alle Entitäten unter einem Gerät."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HaierModbusCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="Haier Brauchwasserwärmepumpe",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def _regs(self) -> dict[int, int]:
        return self.coordinator.data or {}
