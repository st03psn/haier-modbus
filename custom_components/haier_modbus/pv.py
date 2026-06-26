"""Optionale PV-Überschuss-Steuerung innerhalb der Integration.

Regelt die Solltemperatur (Reg 6) dreistufig nach **verfügbarem** Solarstrom
``verfügbar = PV-Überschuss + aktuelle WP-Leistungsaufnahme``. Diese Summe ist
unabhängig davon, ob die WP gerade läuft (schaltet die WP ein, sinkt der
Überschuss um genau ihren Verbrauch, der hier wieder dazukommt) -> kein Pendeln.

Hochschalten erfolgt, sobald der verfügbare Solarstrom die Schwelle deckt;
zurückgeschaltet wird mit **Hysterese** (Rückschalt-Schwelle = Einschalt-Schwelle
- Hysterese). Zusätzlich **Anti-Takt-Schutz**: ein neuer Verdichter-Zyklus startet
erst nach einem Mindest-Stillstand; läuft die WP bereits, wird die Stufe nur
verlängert (Piggyback). Optional wird bei hohem Überschuss zusätzlich **Boost**
und/oder der **Heizstab** (Modus ELEC) zugeschaltet.

Auswertung pro Coordinator-Zyklus; Schreibzugriffe sind idempotent (nur bei
tatsächlicher Abweichung). Anders als eine flankengesteuerte Automation wird hier
jeder Zyklus neu bewertet -> eine durch die Anti-Takt-Sperre verzögerte Stufe
greift automatisch, sobald die Sperre abgelaufen ist.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import homeassistant.util.dt as dt_util

from .const import (
    BIT_BOOST,
    CONF_PV_BOOST,
    CONF_PV_BWWP_SENSOR,
    CONF_PV_DEBOUNCE,
    CONF_PV_ENABLED,
    CONF_PV_FORCE_ELEC,
    CONF_PV_HIGH,
    CONF_PV_HYSTERESIS,
    CONF_PV_MIN_OFF,
    CONF_PV_NORMAL,
    CONF_PV_SENSOR,
    CONF_PV_TEMP_BASE,
    CONF_PV_TEMP_HIGH,
    CONF_PV_TEMP_NORMAL,
    DEFAULT_PV_DEBOUNCE,
    DEFAULT_PV_HIGH,
    DEFAULT_PV_HYSTERESIS,
    DEFAULT_PV_MIN_OFF,
    DEFAULT_PV_NORMAL,
    DEFAULT_PV_TEMP_BASE,
    DEFAULT_PV_TEMP_HIGH,
    DEFAULT_PV_TEMP_NORMAL,
    DOMAIN,
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

# HA-Logbuch-Event (entkoppelt vom logbook-Component, stabiler String).
_EVENT_LOGBOOK_ENTRY = "logbook_entry"


class PvController:
    """Regelt Solltemperatur (+ optional Boost/Heizstab) nach verfügbarem Solarstrom."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._candidate: str | None = None     # entprellter Stufen-Kandidat (high/normal/base)
        self._since = None
        self._boost_applied = False            # Boost von uns gesetzt?
        self._prev_mode: int | None = None     # Modus vor erzwungenem ELEC
        self._off_since = None                 # Zeitpunkt, seit dem der Verdichter aus ist
        self._was_running: bool | None = None  # Verdichter im Vorzyklus?
        self._last_logged: int | None = None   # zuletzt ins Logbuch gemeldete Zielstufe
        self._setpoint_eid: str | None = None  # entity_id der Solltemperatur (Logbuch-Verlinkung)

    def _reset(self) -> None:
        self._candidate = None
        self._since = None

    def _announce(self, coordinator, target: int, avail: float, up: bool) -> None:
        """Stufenwechsel ins HA-Logbuch schreiben – nur bei echtem Wechsel (Dedup),
        also wenige Einträge/Tag, kein Logstorm."""
        if target == self._last_logged:
            return
        self._last_logged = target
        if self._setpoint_eid is None:
            self._setpoint_eid = er.async_get(self.hass).async_get_entity_id(
                "number", DOMAIN, f"{coordinator.entry.entry_id}_set_temp"
            )
        verb = "angehoben" if up else "abgesenkt"
        payload = {
            "name": "BWWP PV-Überschuss",
            "message": f"Ziel {verb} auf {target} °C (verfügbar {avail:.0f} W)",
            "domain": DOMAIN,
        }
        if self._setpoint_eid:
            payload["entity_id"] = self._setpoint_eid
        self.hass.bus.async_fire(_EVENT_LOGBOOK_ENTRY, payload)

    def _temps(self, o: dict) -> tuple[float, float, float]:
        return (
            float(o.get(CONF_PV_TEMP_HIGH, DEFAULT_PV_TEMP_HIGH)),
            float(o.get(CONF_PV_TEMP_NORMAL, DEFAULT_PV_TEMP_NORMAL)),
            float(o.get(CONF_PV_TEMP_BASE, DEFAULT_PV_TEMP_BASE)),
        )

    def _tier(self, o: dict, avail: float, current: float) -> str:
        """Gewünschte Stufe (high/normal/base) mit Hysterese, je nach aktuellem Ziel.

        Hochschalten an den Einschalt-Schwellen (normal/high), Rückschalten erst,
        wenn der verfügbare Solarstrom um die Hysterese darunter fällt.
        """
        high = float(o.get(CONF_PV_HIGH, DEFAULT_PV_HIGH))
        normal = float(o.get(CONF_PV_NORMAL, DEFAULT_PV_NORMAL))
        hyst = float(o.get(CONF_PV_HYSTERESIS, DEFAULT_PV_HYSTERESIS))
        t_high, t_normal, _ = self._temps(o)

        if current >= t_high - 0.5:        # aktuell Hochstufe
            if avail < high - hyst:
                return "normal" if avail >= normal - hyst else "base"
            return "high"
        if current >= t_normal - 0.5:      # aktuell Normalstufe
            if avail >= high:
                return "high"
            if avail < normal - hyst:
                return "base"
            return "normal"
        # aktuell Grundstufe
        if avail >= high:
            return "high"
        if avail >= normal:
            return "normal"
        return "base"

    def _target_for(self, o: dict, tier: str) -> float:
        t_high, t_normal, t_base = self._temps(o)
        target = {"high": t_high, "normal": t_normal, "base": t_base}[tier]
        return float(min(max(int(target), SET_TEMP_MIN), SET_TEMP_MAX))

    def _start_allowed(self, o: dict, running: bool, now) -> bool:
        """Anti-Takt: läuft die WP -> Piggyback; sonst nur nach Mindest-Stillstand."""
        if running:
            return True
        if self._off_since is None:        # war schon vor Beobachtungsbeginn aus
            return True
        min_off_s = o.get(CONF_PV_MIN_OFF, DEFAULT_PV_MIN_OFF) * 60
        return (now - self._off_since).total_seconds() >= min_off_s

    async def async_evaluate(self, coordinator, data: dict[int, int]) -> None:
        o = coordinator.entry.options
        if not o.get(CONF_PV_ENABLED, False):
            self._reset()
            return

        pv = state_float(self.hass, o.get(CONF_PV_SENSOR))
        if pv is None:
            return
        # Verfügbarer Solarstrom = Überschuss + aktuelle WP-Aufnahme (WP-Sensor optional).
        bwwp = state_float(self.hass, o.get(CONF_PV_BWWP_SENSOR)) or 0.0
        avail = pv + bwwp

        now = dt_util.now()
        running = bool((data.get(REG_STATUS) or 0) & STATUS_HEATPUMP)
        # Stillstand-Zeitstempel pflegen (für Anti-Takt): nur beim Übergang an->aus setzen.
        if running:
            self._off_since = None
        elif self._was_running:
            self._off_since = now
        self._was_running = running

        current = data.get(REG_SET_TEMP)
        if current is None:
            return
        current = float(current)

        tier = self._tier(o, avail, current)
        desired = self._target_for(o, tier)

        # Stufe muss erst die Entprellzeit lang stabil sein.
        if self._candidate != tier:
            self._candidate = tier
            self._since = now
            return
        debounce_s = o.get(CONF_PV_DEBOUNCE, DEFAULT_PV_DEBOUNCE) * 60
        if self._since is None or (now - self._since).total_seconds() < debounce_s:
            return

        # Solltemperatur: Herunterregeln immer; Hochregeln nur wenn Speicher unter
        # Ziel UND Anti-Takt es erlaubt (idempotent).
        if int(current) != int(desired):
            if desired < current:
                await coordinator.write_value(REG_SET_TEMP, int(desired))
                _LOGGER.debug("PV: Soll %d -> %d (runter, verfügbar %.0f W)",
                              int(current), int(desired), avail)
                self._announce(coordinator, int(desired), avail, up=False)
            else:
                water = data.get(REG_WATER_TEMP)
                if (water is not None and float(water) < desired
                        and self._start_allowed(o, running, now)):
                    await coordinator.write_value(REG_SET_TEMP, int(desired))
                    _LOGGER.debug("PV: Soll %d -> %d (hoch, verfügbar %.0f W, %s)",
                                  int(current), int(desired), avail,
                                  "WP läuft" if running else "Stillstand ok")
                    self._announce(coordinator, int(desired), avail, up=True)

        # Eskalation bei hohem Überschuss – nur im Betrieb (idempotent).
        await self._apply_escalation(coordinator, o, data, tier == "high" and running, avail)

    async def _apply_escalation(self, coordinator, o, data, high: bool, avail: float) -> None:
        # Boost
        if o.get(CONF_PV_BOOST, False):
            func = data.get(REG_FUNCTION)
            if func is not None:
                on = bool(func & BIT_BOOST)
                if high and not on:
                    await coordinator.write_value(REG_FUNCTION, func | BIT_BOOST)
                    self._boost_applied = True
                    _LOGGER.debug("PV: Boost an (verfügbar %.0f W)", avail)
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
                    _LOGGER.debug("PV: Modus -> ELEC (Heizstab, verfügbar %.0f W)", avail)
                elif not high and mode == MODE_ELEC and self._prev_mode is not None:
                    await coordinator.write_value(REG_MODE, self._prev_mode)
                    _LOGGER.debug("PV: Modus zurück -> %s", self._prev_mode)
                    self._prev_mode = None
