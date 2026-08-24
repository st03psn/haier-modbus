"""Selects: Betriebsmodus (Reg 1, RW) und – im Executor-Modus – das PV-Programm.

Das PV-Programm (``select.haier_hwhp_pv_program``) ist die Hoch-Ebene für ein
externes HEMS: es setzt ein Programm (aus/grund/ueberschuss/boost), die Integration
übersetzt das idempotent in die Mechanik (Sollwert/Modus/Boost). Es wird nur im
**Executor**-Modus angelegt – in Aus/Coordinator existiert es nicht (Reload bei
Options-Änderung legt es bei Bedarf neu an).
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    BIT_BOOST,
    CONF_EMERGENCY_MODE,
    CONF_PV_ESCALATION,
    CONF_PV_MODE,
    CONF_PV_TEMP_BASE,
    CONF_PV_TEMP_HIGH,
    CONF_PV_TEMP_NORMAL,
    DEFAULT_EMERGENCY_MODE,
    DEFAULT_PV_ESCALATION,
    DEFAULT_PV_TEMP_BASE,
    DEFAULT_PV_TEMP_HIGH,
    DEFAULT_PV_TEMP_NORMAL,
    DOMAIN,
    EMERGENCY_MODE_AUTO,
    EMERGENCY_MODE_ELEC,
    MODE_AUTO,
    MODE_ECO,
    MODE_TO_TEXT,
    PV_ESC_BOOST,
    PV_ESC_NONE,
    PV_MODE_COORDINATOR,
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
    WP_MAX_TEMP,
)
from .entity import HaierModbusEntity


@dataclass(frozen=True, kw_only=True)
class OptionSelect:
    """Beschreibung einer Select-Fassade auf einen enum-artigen Options-Schlüssel."""

    key: str
    default: str
    options: tuple[str, ...]
    icon: str | None = None


# Notheizung: unabhängig vom PV-Modus, unconditional angelegt.
EMERGENCY_SELECTS: tuple[OptionSelect, ...] = (
    OptionSelect(key=CONF_EMERGENCY_MODE, default=DEFAULT_EMERGENCY_MODE,
                 options=(EMERGENCY_MODE_AUTO, EMERGENCY_MODE_ELEC),
                 icon="mdi:fire-alert"),
)

# PV-Eskalation: nur im Coordinator-Modus relevant (Boost ist dort eine echte Stufe).
# Bewusst OHNE den Altwert "elec" - der ist reines Migrationsziel für Altbestand
# (__init__.py-Migration bildet ihn auf "boost" ab) und im aktiven Options-Flow-
# Selector selbst schon nicht mehr enthalten.
PV_COORDINATOR_SELECTS: tuple[OptionSelect, ...] = (
    OptionSelect(key=CONF_PV_ESCALATION, default=DEFAULT_PV_ESCALATION,
                 options=(PV_ESC_NONE, PV_ESC_BOOST), icon="mdi:tune"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [HaierModeSelect(coordinator)]
    if entry.options.get(CONF_PV_MODE) == PV_MODE_EXECUTOR:
        entities.append(HaierPvProgramSelect(coordinator))
    entities += [HaierOptionSelect(coordinator, d) for d in EMERGENCY_SELECTS]
    if entry.options.get(CONF_PV_MODE) == PV_MODE_COORDINATOR:
        entities += [HaierOptionSelect(coordinator, d) for d in PV_COORDINATOR_SELECTS]
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


class HaierPvProgramSelect(HaierModbusEntity, RestoreEntity, SelectEntity):
    """PV-Programm (Executor): aus/grund/ueberschuss/boost -> Sollwert/Modus/Boost.

    Reines Kommando-Select (kein Register hält ein "Programm"); ``current_option``
    spiegelt das zuletzt in dieser Sitzung gesetzte Programm. Idempotente Writes beim
    Setzen, kein Dauer-Loop nötig (Event-getrieben durch HEMS/Nutzer).

    C4: ``RestoreEntity`` - ohne das zeigte ein Reload das Programm als "aus",
    während das Gerät noch auf dem zuletzt gesetzten Sollwert (ggf. + Boost)
    stand. Wirkt wie Zustandsverlust, obwohl die Mechanik selbst unverändert
    weiterläuft (dieses Select besitzt kein Register).
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

    async def async_added_to_hass(self) -> None:
        """C4: letztes gesetztes Programm nach Reload/Neustart wiederherstellen."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state

    def _temps(self) -> tuple[int, int, int]:
        """(Basis, Erhöht, Boost) - Ordnungsklemme analog ``pv.py._temps()`` (W10/C5).

        Der Options-Flow hat keine Cross-Field-Validierung, die Number-Entities
        ändern je ein Feld einzeln (docs/-Fallstricke) - eine verdrehte Konfiguration
        (z. B. ``pv_temp_high`` < ``pv_temp_normal``) darf das Programm "boost" nicht
        dazu bringen, den Sollwert UNTER "ueberschuss" abzusenken. Basis/Erhöht
        zusätzlich auf ``WP_MAX_TEMP`` begrenzt (Regel 3): beide müssen der
        Verdichter allein erreichen, die Programme setzen dafür ECO/AUTO ohne
        Boost-Bit.
        """
        o = self.coordinator.entry.options
        base = int(o.get(CONF_PV_TEMP_BASE, DEFAULT_PV_TEMP_BASE))
        normal = int(o.get(CONF_PV_TEMP_NORMAL, DEFAULT_PV_TEMP_NORMAL))
        high = int(o.get(CONF_PV_TEMP_HIGH, DEFAULT_PV_TEMP_HIGH))
        base = min(max(base, SET_TEMP_MIN), WP_MAX_TEMP)
        normal = min(max(normal, base), WP_MAX_TEMP)
        high = min(max(high, normal), SET_TEMP_MAX)
        return base, normal, high

    async def async_select_option(self, option: str) -> None:
        if option not in self._attr_options:
            return
        if not await self._apply(option):
            # W8: Rückgabewert von ``write_value`` jetzt ausgewertet - lehnt das
            # Gerät ab, darf das Select nicht trotzdem "boost" anzeigen (ein
            # HEMS/evcc läse das als Bestätigung, obwohl Sollwert/Boost-Bit
            # unverändert blieben).
            raise HomeAssistantError(
                f"PV-Programm '{option}' konnte nicht vollständig angewendet werden"
            )
        self._attr_current_option = option
        self.async_write_ha_state()

    async def _apply(self, option: str) -> bool:
        if option == PV_PROGRAM_OFF:
            return True  # Integration fasst den Sollwert nicht an (manuell/Gerät)

        base, normal, high = self._temps()
        # W9: ohne bislang erfolgreichen Block-Read ist ``REG_FUNCTION`` unbekannt -
        # ein Fallback auf 0 würde beim Schreiben ALLE fremden Bits löschen
        # (BIT_ACTIVE/BIT_MUTE/BIT_STERILIZE), das Gerät ginge aus. Vorlage:
        # ``pv._apply_heater`` verweigert unter derselben Bedingung ebenfalls.
        func = self._regs.get(REG_FUNCTION)
        ok = True
        if option == PV_PROGRAM_GRUND:
            ok &= await self.coordinator.write_value(REG_MODE, MODE_ECO)
            ok &= await self.coordinator.write_value(REG_SET_TEMP, base)
            if func is None:
                ok = False
            elif func & BIT_BOOST:
                ok &= await self.coordinator.write_value(REG_FUNCTION, func & ~BIT_BOOST)
        elif option == PV_PROGRAM_UEBERSCHUSS:
            # AUTO überwindet den ECO-Deadband sofort.
            ok &= await self.coordinator.write_value(REG_MODE, MODE_AUTO)
            ok &= await self.coordinator.write_value(REG_SET_TEMP, normal)
            if func is None:
                ok = False
            elif func & BIT_BOOST:
                ok &= await self.coordinator.write_value(REG_FUNCTION, func & ~BIT_BOOST)
        elif option == PV_PROGRAM_BOOST:
            ok &= await self.coordinator.write_value(REG_SET_TEMP, high)
            if func is None:
                ok = False
            elif not (func & BIT_BOOST):
                ok &= await self.coordinator.write_value(REG_FUNCTION, func | BIT_BOOST)

        await self.coordinator.async_request_refresh()
        return ok


class HaierOptionSelect(HaierModbusEntity, SelectEntity):
    """Bedien-Fassade auf einen enum-artigen Options-Schlüssel in ``entry.options``
    (``emergency_mode``, ``pv_escalation``) – Muster analog ``HaierPvOptionNumber``
    in ``number.py``. Anders als ``HaierPvProgramSelect`` kein Kommando-Select,
    sondern ein reiner Options-Spiegel: liest/schreibt den Schlüssel direkt.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, desc: OptionSelect) -> None:
        super().__init__(coordinator)
        self._desc = desc
        self._attr_translation_key = desc.key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{desc.key}"
        self._attr_options = list(desc.options)
        self._attr_icon = desc.icon

    @property
    def available(self) -> bool:
        """Config-Entity: auch bei Modbus-Störung einsehbar/änderbar."""
        return True

    @property
    def current_option(self) -> str | None:
        return self.coordinator.entry.options.get(self._desc.key, self._desc.default)

    async def async_select_option(self, option: str) -> None:
        entry = self.coordinator.entry
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, self._desc.key: option}
        )
        # Ohne Reload bleibt diese Entität bestehen -> Zustand selbst nachziehen.
        self.async_write_ha_state()
