"""Time: Uhrzeit-Fenster als Options-Fassade (Legionellen-ECO-Fenster).

Erste ``time``-Plattform der Integration. Speicherformat bleibt der bestehende
``"HH:MM"``-String in ``entry.options`` (kompatibel mit
``legionella._parse_time`` – keine Änderung an der Regelungslogik nötig), diese
Entities sind wie die anderen Options-Fassaden nur Bedien-/Sicht-Fassaden darauf.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_LEGIONELLA_WINDOW_END,
    CONF_LEGIONELLA_WINDOW_START,
    DEFAULT_LEGIONELLA_WINDOW_END,
    DEFAULT_LEGIONELLA_WINDOW_START,
    DOMAIN,
)
from .entity import HaierModbusEntity


@dataclass(frozen=True, kw_only=True)
class OptionTime:
    """Beschreibung einer Time-Fassade auf einen ``"HH:MM"``-Options-Schlüssel."""

    key: str
    default: str
    icon: str | None = None


# Legionellen-ECO-Fenster: unabhängig vom PV-Modus, unconditional angelegt.
LEGIONELLA_TIMES: tuple[OptionTime, ...] = (
    OptionTime(key=CONF_LEGIONELLA_WINDOW_START, default=DEFAULT_LEGIONELLA_WINDOW_START,
               icon="mdi:clock-start"),
    OptionTime(key=CONF_LEGIONELLA_WINDOW_END, default=DEFAULT_LEGIONELLA_WINDOW_END,
               icon="mdi:clock-end"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(HaierOptionTime(coordinator, d) for d in LEGIONELLA_TIMES)


class HaierOptionTime(HaierModbusEntity, TimeEntity):
    """Bedien-Fassade auf einen Uhrzeit-Options-Schlüssel in ``entry.options``."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, desc: OptionTime) -> None:
        super().__init__(coordinator)
        self._desc = desc
        self._attr_translation_key = desc.key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{desc.key}"
        self._attr_icon = desc.icon

    @property
    def available(self) -> bool:
        """Config-Entity: auch bei Modbus-Störung einsehbar/änderbar."""
        return True

    @property
    def native_value(self) -> time | None:
        raw = self.coordinator.entry.options.get(self._desc.key, self._desc.default)
        try:
            h, m = str(raw).split(":")[:2]
            return time(int(h), int(m))
        except (ValueError, IndexError):
            return None

    async def async_set_value(self, value: time) -> None:
        entry = self.coordinator.entry
        raw = f"{value.hour:02d}:{value.minute:02d}"
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, self._desc.key: raw}
        )
        # Ohne Reload bleibt diese Entität bestehen -> Zustand selbst nachziehen.
        self.async_write_ha_state()
