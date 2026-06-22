"""Number: Solltemperatur (Register 6, RW)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, REG_SET_TEMP, SET_TEMP_MAX, SET_TEMP_MIN
from .entity import HaierModbusEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HaierSetTemperature(coordinator)])


class HaierSetTemperature(HaierModbusEntity, NumberEntity):
    _attr_translation_key = "set_temp"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = SET_TEMP_MIN
    _attr_native_max_value = SET_TEMP_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:thermometer-water"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_set_temp"

    @property
    def native_value(self) -> float | None:
        return self._regs.get(REG_SET_TEMP)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_register(REG_SET_TEMP, int(value))
