"""Optionale PV-Überschuss-Steuerung innerhalb der Integration.

Setzt die Solltemperatur (Reg 6) dreistufig nach PV-Überschuss; optional wird bei
hohem Überschuss zusätzlich **Boost** aktiviert und/oder der **Heizstab** über
Modus ELEC zugeschaltet, um den Überschuss maximal zu nutzen. Auswertung pro
Coordinator-Zyklus; eine Stufe greift erst nach der Entprellzeit. Schreibzugriffe
sind idempotent (nur bei tatsächlicher Abweichung).
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
import homeassistant.util.dt as dt_util

from .const import (
    BIT_BOOST,
    CONF_PV_BOOST,
    CONF_PV_DEBOUNCE,
    CONF_PV_ENABLED,
    CONF_PV_FORCE_ELEC,
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
    MODE_ELEC,
    REG_FUNCTION,
    REG_MODE,
    REG_SET_TEMP,
    REG_STATUS,
    REG_WATER_TEMP,
    SET_TEMP_MAX,
    SET_TEMP_MIN,
    STATUS_HEATPUMP,
)
from .energy import state_float

_LOGGER = logging.getLogger(__name__)


class PvController:
    """Regelt Solltemperatur (+ optional Boost/Heizstab) nach PV-Überschuss."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._candidate: str | None = None   # Kandidat-Stufe (high/normal/base)
        self._since = None
        self._boost_applied = False           # Boost von uns gesetzt?
        self._prev_mode: int | None = None    # Modus vor erzwungenem ELEC

    def _reset(self) -> None:
        self._candidate = None
        self._since = None

    def _tier_and_temp(self, o: dict, pv: float) -> tuple[str, float]:
        high = o.get(CONF_PV_HIGH, DEFAULT_PV_HIGH)
        normal = o.get(CONF_PV_NORMAL, DEFAULT_PV_NORMAL)
        if pv >= high:
            tier, target = "high", o.get(CONF_PV_TEMP_HIGH, DEFAULT_PV_TEMP_HIGH)
        elif pv >= normal:
            tier, target = "normal", o.get(CONF_PV_TEMP_NORMAL, DEFAULT_PV_TEMP_NORMAL)
        else:
            tier, target = "base", o.get(CONF_PV_TEMP_BASE, DEFAULT_PV_TEMP_BASE)
        return tier, float(min(max(int(target), SET_TEMP_MIN), SET_TEMP_MAX))

    async def async_evaluate(self, coordinator, data: dict[int, int]) -> None:
        o = coordinator.entry.options
        if not o.get(CONF_PV_ENABLED, False):
            self._reset()
            return

        pv = state_float(self.hass, o.get(CONF_PV_SENSOR))
        if pv is None:
            return

        tier, desired = self._tier_and_temp(o, pv)
        now = dt_util.now()

        # Stufe muss erst die Entprellzeit lang stabil sein.
        if self._candidate != tier:
            self._candidate = tier
            self._since = now
            return
        debounce_s = o.get(CONF_PV_DEBOUNCE, DEFAULT_PV_DEBOUNCE) * 60
        if self._since is None or (now - self._since).total_seconds() < debounce_s:
            return

        # Überschuss-Logik greift nur, während die WP läuft (Reg 3, bit0).
        # Ausnahme: Herunterregeln/Boost-aus läuft immer (Aufräumen).
        running = bool((data.get(REG_STATUS) or 0) & STATUS_HEATPUMP)

        # 1) Solltemperatur: Hochregeln nur im Betrieb + wenn Speicher unter Ziel;
        #    Herunterregeln (zur Grundtemperatur) immer.
        current = data.get(REG_SET_TEMP)
        water = data.get(REG_WATER_TEMP)
        if current is not None and int(current) != int(desired):
            lowering = desired < current
            if lowering:
                await coordinator.write_value(REG_SET_TEMP, int(desired))
                _LOGGER.debug("PV: Soll %s -> %s (runter)", current, desired)
            elif running and (water is not None and water < desired):
                await coordinator.write_value(REG_SET_TEMP, int(desired))
                _LOGGER.debug("PV: Soll %s -> %s (PV %.0f W, WP läuft)", current, desired, pv)

        # 2) Eskalation bei hohem Überschuss – nur im Betrieb (idempotent).
        await self._apply_escalation(coordinator, o, data, tier == "high" and running, pv)

    async def _apply_escalation(self, coordinator, o, data, high: bool, pv: float) -> None:
        # Boost
        if o.get(CONF_PV_BOOST, False):
            func = data.get(REG_FUNCTION)
            if func is not None:
                on = bool(func & BIT_BOOST)
                if high and not on:
                    await coordinator.write_value(REG_FUNCTION, func | BIT_BOOST)
                    self._boost_applied = True
                    _LOGGER.debug("PV: Boost an (PV %.0f W)", pv)
                elif not high and on and self._boost_applied:
                    await coordinator.write_value(REG_FUNCTION, func & ~BIT_BOOST)
                    self._boost_applied = False
                    _LOGGER.debug("PV: Boost aus")

        # Heizstab via Modus ELEC
        if o.get(CONF_PV_FORCE_ELEC):
            mode = data.get(REG_MODE)
            if mode is not None:
                if high and mode != MODE_ELEC:
                    self._prev_mode = mode
                    await coordinator.write_value(REG_MODE, MODE_ELEC)
                    _LOGGER.debug("PV: Modus -> ELEC (Heizstab, PV %.0f W)", pv)
                elif not high and mode == MODE_ELEC and self._prev_mode is not None:
                    await coordinator.write_value(REG_MODE, self._prev_mode)
                    _LOGGER.debug("PV: Modus zurück -> %s", self._prev_mode)
                    self._prev_mode = None
