"""water_heater: zentrale Bedienkachel (Ist/Soll + Modus)."""

from __future__ import annotations

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    MODE_TO_TEXT,
    REG_MODE,
    REG_SET_TEMP,
    REG_WATER_TEMP,
    SET_TEMP_MAX,
    SET_TEMP_MIN,
    TEXT_TO_MODE,
)
from .entity import HaierModbusEntity

# Geräte-Modi als Klartext-Operationen der water_heater-Kachel.
OPERATIONS = list(TEXT_TO_MODE.keys())  # AUTO, ECO, ELEC, VAC


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HaierWaterHeater(coordinator)])


class HaierWaterHeater(HaierModbusEntity, WaterHeaterEntity):
    _attr_name = None  # nutzt den Gerätenamen als Kachelnamen
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = SET_TEMP_MIN
    _attr_max_temp = SET_TEMP_MAX
    _attr_target_temperature_step = 1  # Modbus-Register ist ganzzahlig (keine 0,5°)
    _attr_operation_list = OPERATIONS
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_water_heater"

    @property
    def current_temperature(self) -> float | None:
        return self._regs.get(REG_WATER_TEMP)

    @property
    def target_temperature(self) -> float | None:
        return self._regs.get(REG_SET_TEMP)

    @property
    def current_operation(self) -> str | None:
        return MODE_TO_TEXT.get(self._regs.get(REG_MODE, -1))

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            await self.coordinator.async_write_register(REG_SET_TEMP, int(temp))

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        value = TEXT_TO_MODE.get(operation_mode)
        if value is not None:
            await self.coordinator.async_write_register(REG_MODE, value)
