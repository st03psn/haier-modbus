"""Gemeinsame Entity-Basis mit Geräteinfo."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MODEL, DOMAIN, MANUFACTURER, MODEL, MODELS, localized_title
from .coordinator import HaierModbusCoordinator


class HaierModbusEntity(CoordinatorEntity[HaierModbusCoordinator]):
    """Basisklasse – bündelt alle Entitäten unter einem Gerät."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: HaierModbusCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.entry
        model_key = entry.options.get(CONF_MODEL, entry.data.get(CONF_MODEL))
        model = MODELS.get(model_key) or model_key or MODEL
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=localized_title(coordinator.hass.config.language),
            manufacturer=MANUFACTURER,
            model=model,
        )

    @property
    def _regs(self) -> dict[int, int]:
        return self.coordinator.data or {}
