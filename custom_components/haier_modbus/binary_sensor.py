"""Binärsensoren: Betriebsstatus-Bits (Register 3) + Verbindung."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    REG_STATUS,
    STATUS_BOILER,
    STATUS_EHEATER,
    STATUS_HEATPUMP,
    STATUS_SOLAR,
)
from .entity import HaierModbusEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            HaierStatusBit(coordinator, "wp", STATUS_HEATPUMP, "mdi:heat-pump"),
            HaierStatusBit(coordinator, "heater", STATUS_EHEATER, "mdi:radiator"),
            HaierStatusBit(coordinator, "solar", STATUS_SOLAR, "mdi:solar-power"),
            HaierStatusBit(coordinator, "boiler", STATUS_BOILER, "mdi:water-boiler"),
            HaierConnection(coordinator),
        ]
    )


class HaierStatusBit(HaierModbusEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator, key: str, bitmask: int, icon: str) -> None:
        super().__init__(coordinator)
        self._bitmask = bitmask
        self._attr_translation_key = f"status_{key}"
        self._attr_icon = icon
        self._attr_unique_id = f"{coordinator.entry.entry_id}_status_{key}"

    @property
    def is_on(self) -> bool | None:
        raw = self._regs.get(REG_STATUS)
        return None if raw is None else bool(raw & self._bitmask)


class HaierConnection(HaierModbusEntity, BinarySensorEntity):
    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = None

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_connection"

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def available(self) -> bool:
        return True
