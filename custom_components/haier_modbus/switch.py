"""Switches: einzelne Bits im Funktionsregister (Register 2, RW)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BIT_ACTIVE,
    BIT_BOOST,
    BIT_MUTE,
    BIT_STERILIZE,
    DOMAIN,
    REG_FUNCTION,
)
from .entity import HaierModbusEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            HaierBitSwitch(coordinator, "active", BIT_ACTIVE, "mdi:power"),
            HaierBitSwitch(coordinator, "boost", BIT_BOOST, "mdi:rocket-launch"),
            HaierBitSwitch(coordinator, "mute", BIT_MUTE, "mdi:volume-mute"),
            HaierBitSwitch(coordinator, "sterilize", BIT_STERILIZE, "mdi:bacteria"),
        ]
    )


class HaierBitSwitch(HaierModbusEntity, SwitchEntity):
    """Setzt/löscht ein Bit im Funktionsregister."""

    def __init__(self, coordinator, key: str, bitmask: int, icon: str) -> None:
        super().__init__(coordinator)
        self._bitmask = bitmask
        self._attr_translation_key = key
        self._attr_icon = icon
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"

    @property
    def is_on(self) -> bool | None:
        raw = self._regs.get(REG_FUNCTION)
        return None if raw is None else bool(raw & self._bitmask)

    async def async_turn_on(self, **kwargs) -> None:
        current = self._regs.get(REG_FUNCTION, 0)
        await self.coordinator.async_write_register(REG_FUNCTION, current | self._bitmask)

    async def async_turn_off(self, **kwargs) -> None:
        current = self._regs.get(REG_FUNCTION, 0)
        await self.coordinator.async_write_register(REG_FUNCTION, current & ~self._bitmask)
