"""Selects: Betriebsmodus (Reg 1, RW) und – im Executor-Modus – das PV-Programm.

Das PV-Programm (``select.haier_hwhp_pv_program``) ist die Hoch-Ebene für ein
externes HEMS: es setzt ein Programm (aus/grund/ueberschuss/boost), die Integration
übersetzt das idempotent in die Mechanik (Sollwert/Modus/Boost). Es wird nur im
**Executor**-Modus angelegt – in Aus/Coordinator existiert es nicht (Reload bei
Options-Änderung legt es bei Bedarf neu an).
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BIT_BOOST,
    CONF_PV_MODE,
    CONF_PV_TEMP_BASE,
    CONF_PV_TEMP_HIGH,
    CONF_PV_TEMP_NORMAL,
    DEFAULT_PV_TEMP_BASE,
    DEFAULT_PV_TEMP_HIGH,
    DEFAULT_PV_TEMP_NORMAL,
    DOMAIN,
    MODE_AUTO,
    MODE_ECO,
    MODE_TO_TEXT,
    PV_MODE_EXECUTOR,
    PV_PROGRAM_BOOST,
    PV_PROGRAM_GRUND,
    PV_PROGRAM_OFF,
    PV_PROGRAM_UEBERSCHUSS,
    REG_FUNCTION,
    REG_MODE,
    REG_SET_TEMP,
    SET_TEMP_MAX,
    SET_TEMP_MIN,
    TEXT_TO_MODE,
)
from .entity import HaierModbusEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [HaierModeSelect(coordinator)]
    if entry.options.get(CONF_PV_MODE) == PV_MODE_EXECUTOR:
        entities.append(HaierPvProgramSelect(coordinator))
    async_add_entities(entities)


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


class HaierPvProgramSelect(HaierModbusEntity, SelectEntity):
    """PV-Programm (Executor): aus/grund/ueberschuss/boost -> Sollwert/Modus/Boost.

    Reines Kommando-Select (kein Register hält ein "Programm"); ``current_option``
    spiegelt das zuletzt in dieser Sitzung gesetzte Programm. Idempotente Writes beim
    Setzen, kein Dauer-Loop nötig (Event-getrieben durch HEMS/Nutzer).
    """

    _attr_translation_key = "pv_program"
    _attr_icon = "mdi:solar-power-variant"
    _attr_options = [
        PV_PROGRAM_OFF,
        PV_PROGRAM_GRUND,
        PV_PROGRAM_UEBERSCHUSS,
        PV_PROGRAM_BOOST,
    ]

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_pv_program"
        self._attr_current_option = PV_PROGRAM_OFF

    def _temp(self, key: str, default: int) -> int:
        raw = int(self.coordinator.entry.options.get(key, default))
        return min(max(raw, SET_TEMP_MIN), SET_TEMP_MAX)

    async def async_select_option(self, option: str) -> None:
        if option not in self._attr_options:
            return
        await self._apply(option)
        self._attr_current_option = option
        self.async_write_ha_state()

    async def _apply(self, option: str) -> None:
        if option == PV_PROGRAM_OFF:
            return  # Integration fasst den Sollwert nicht an (manuell/Gerät)

        func = self._regs.get(REG_FUNCTION, 0) or 0
        if option == PV_PROGRAM_GRUND:
            await self.coordinator.write_value(REG_MODE, MODE_ECO)
            await self.coordinator.write_value(
                REG_SET_TEMP, self._temp(CONF_PV_TEMP_BASE, DEFAULT_PV_TEMP_BASE)
            )
            if func & BIT_BOOST:
                await self.coordinator.write_value(REG_FUNCTION, func & ~BIT_BOOST)
        elif option == PV_PROGRAM_UEBERSCHUSS:
            # AUTO überwindet den ECO-Deadband sofort.
            await self.coordinator.write_value(REG_MODE, MODE_AUTO)
            await self.coordinator.write_value(
                REG_SET_TEMP, self._temp(CONF_PV_TEMP_NORMAL, DEFAULT_PV_TEMP_NORMAL)
            )
            if func & BIT_BOOST:
                await self.coordinator.write_value(REG_FUNCTION, func & ~BIT_BOOST)
        elif option == PV_PROGRAM_BOOST:
            await self.coordinator.write_value(
                REG_SET_TEMP, self._temp(CONF_PV_TEMP_HIGH, DEFAULT_PV_TEMP_HIGH)
            )
            if not (func & BIT_BOOST):
                await self.coordinator.write_value(REG_FUNCTION, func | BIT_BOOST)

        await self.coordinator.async_request_refresh()
