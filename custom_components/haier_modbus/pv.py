"""Optionale PV-Überschuss-Steuerung innerhalb der Integration.

Setzt die Solltemperatur (Reg 6) dreistufig nach PV-Überschuss – wie der
mitgelieferte Blueprint, aber direkt in der Integration und im Setup-/Options-
Flow konfigurierbar. Wird pro Coordinator-Zyklus ausgewertet; eine Stufe greift
erst nach Ablauf der Entprellzeit, und nur wenn nötig (Hochregeln nur, solange
der Speicher unter der Zielstufe liegt; Herunterregeln immer).
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

from .const import (
    CONF_PV_DEBOUNCE,
    CONF_PV_ENABLED,
    CONF_PV_HIGH,
    CONF_PV_NORMAL,
    CONF_PV_SENSOR,
    CONF_PV_TEMP_BASE,
    CONF_PV_TEMP_HIGH,
    CONF_PV_TEMP_NORMAL,
    DEFAULT_PV_DEBOUNCE,
    DEFAULT_PV_HIGH,
    DEFAULT_PV_NORMAL,
    DEFAULT_PV_TEMP_BASE,
    DEFAULT_PV_TEMP_HIGH,
    DEFAULT_PV_TEMP_NORMAL,
    REG_SET_TEMP,
    REG_WATER_TEMP,
    SET_TEMP_MAX,
    SET_TEMP_MIN,
)
from .energy import state_float

_LOGGER = logging.getLogger(__name__)


class PvController:
    """Regelt die Solltemperatur nach PV-Überschuss (zustandsbehaftet)."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._candidate: float | None = None
        self._since = None

    def _desired(self, o: dict, pv: float) -> float:
        high = o.get(CONF_PV_HIGH, DEFAULT_PV_HIGH)
        normal = o.get(CONF_PV_NORMAL, DEFAULT_PV_NORMAL)
        if pv >= high:
            target = o.get(CONF_PV_TEMP_HIGH, DEFAULT_PV_TEMP_HIGH)
        elif pv >= normal:
            target = o.get(CONF_PV_TEMP_NORMAL, DEFAULT_PV_TEMP_NORMAL)
        else:
            target = o.get(CONF_PV_TEMP_BASE, DEFAULT_PV_TEMP_BASE)
        return float(min(max(int(target), SET_TEMP_MIN), SET_TEMP_MAX))

    async def async_evaluate(self, coordinator, data: dict[int, int]) -> None:
        o = coordinator.entry.options
        if not o.get(CONF_PV_ENABLED, False):
            self._candidate = None
            self._since = None
            return

        pv = state_float(self.hass, o.get(CONF_PV_SENSOR))
        if pv is None:
            return

        desired = self._desired(o, pv)
        now = dt_util.now()

        # Stufe muss erst die Entprellzeit lang stabil sein.
        if self._candidate != desired:
            self._candidate = desired
            self._since = now
            return
        debounce_s = o.get(CONF_PV_DEBOUNCE, DEFAULT_PV_DEBOUNCE) * 60
        if self._since is None or (now - self._since).total_seconds() < debounce_s:
            return

        current = data.get(REG_SET_TEMP)
        if current is None or int(current) == int(desired):
            return

        water = data.get(REG_WATER_TEMP)
        # Hochregeln nur, wenn der Speicher noch unter der Zielstufe liegt;
        # Herunterregeln immer (kein Sinn, höher zu halten ohne Überschuss).
        if desired < current or (water is not None and water < desired):
            await coordinator.write_setpoint(int(desired))
            _LOGGER.debug(
                "PV-Steuerung: Solltemperatur %s -> %s (PV %.0f W)", current, desired, pv
            )
