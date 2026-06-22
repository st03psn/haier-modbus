"""Select: Betriebsmodus (Register 1, RW)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MODE_TO_TEXT, REG_MODE, TEXT_TO_MODE
from .entity import HaierModbusEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HaierModeSelect(coordinator)])


class HaierModeSelect(HaierModbusEntity, SelectEntity):
    _attr_translation_key = "mode_select"
    _attr_icon = "mdi:tune-variant"
    _attr_options = list(TEXT_TO_MODE.keys())  # AUTO, ECO, ELEC, VAC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_mode"

    @property
    def current_option(self) -> str | None:
        return MODE_TO_TEXT.get(self._regs.get(REG_MODE, -1))

    async def async_select_option(self, option: str) -> None:
        value = TEXT_TO_MODE.get(option)
        if value is not None:
            await self.coordinator.async_write_register(REG_MODE, value)
