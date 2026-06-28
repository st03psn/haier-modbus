"""Optionale PV-Überschuss-Steuerung (Coordinator-Modus) innerhalb der Integration.

Regelt die Solltemperatur (Reg 6) dreistufig (50/65/75) nach **rohem** PV-Überschuss
(``sensor.pv_uberschuss_watt``, kappt bei 0 -> kein signierter Netzwert). Weil der
Überschuss einbricht, sobald die WP läuft, wird NICHT auf einen "verfügbar"-Wert
geregelt, sondern bewusst pendelfrei gemacht durch:

- **Morgen-Start (fix):** einmal/Tag zur konfigurierten Uhrzeit einen 65er-Kick, wenn
  das Wasser noch unter der Grundtemperatur liegt – startet die WP im ECO-Fenster.
- **Halten/Absenken mit Entprellung:** bei Überschuss über der Halte-Schwelle bei 65
  bleiben; fällt er für die Entprellzeit darunter, zurück auf 50.
- **Wiederanlauf (Option):** kommt tagsüber wieder genug Überschuss, erneut auf 65 –
  mit **Anti-Takt** (Piggyback, solange die WP läuft; sonst erst nach Mindest-Stillstand).
- **75 + Eskalation:** bei sehr hohem Überschuss (Boost/Heizstab) – greift **auch bei
  stehender WP**: Boost startet WP+Heizstab (anti-takt-geschützt), der reine Heizstab
  (ELEC) dumpt sofort ohne Mindest-Stillstand (kein Verdichterzyklus).

Nur im **Coordinator**-Modus aktiv; in **Aus**/**Executor** steigt ``async_evaluate``
sofort aus (``pv.py`` inert). Schreibzugriffe sind idempotent (nur bei Abweichung).
"""

from __future__ import annotations

import logging
from datetime import time

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import homeassistant.util.dt as dt_util

from .const import (
    BIT_BOOST,
    CONF_PV_DEBOUNCE,
    CONF_PV_ESCALATION,
    CONF_PV_HIGH,
    CONF_PV_HOLD,
    CONF_PV_MIN_OFF,
    CONF_PV_MODE,
    CONF_PV_MORNING_ENABLED,
    CONF_PV_MORNING_TIME,
    CONF_PV_RERAISE_ENABLED,
    CONF_PV_RERAISE_THRESHOLD,
    CONF_PV_SENSOR,
    CONF_PV_TEMP_BASE,
    CONF_PV_TEMP_HIGH,
    CONF_PV_TEMP_NORMAL,
    DEFAULT_PV_DEBOUNCE,
    DEFAULT_PV_HIGH,
    DEFAULT_PV_HOLD,
    DEFAULT_PV_MIN_OFF,
    DEFAULT_PV_MORNING_ENABLED,
    DEFAULT_PV_MORNING_TIME,
    DEFAULT_PV_RERAISE_ENABLED,
    DEFAULT_PV_RERAISE_THRESHOLD,
    DEFAULT_PV_TEMP_BASE,
    DEFAULT_PV_TEMP_HIGH,
    DEFAULT_PV_TEMP_NORMAL,
    DOMAIN,
    MODE_ELEC,
    PV_ESC_BOOST,
    PV_ESC_ELEC,
    PV_ESC_NONE,
    PV_MODE_COORDINATOR,
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


def _parse_time(raw) -> time:
    """"HH:MM" / "HH:MM:SS" -> time; bei Unsinn Default 10:00."""
    try:
        parts = str(raw).split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return time(10, 0)


class PvController:
    """Coordinator-Modus: regelt Solltemperatur (+ optional Boost/Heizstab) nach Überschuss."""

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
        self._last_kick_day = None             # Datum des letzten Morgen-Starts (einmal/Tag)

    def _reset(self) -> None:
        self._candidate = None
        self._since = None

    def _announce(self, coordinator, target: int, surplus: float, up: bool) -> None:
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
            "message": f"Ziel {verb} auf {target} °C (Überschuss {surplus:.0f} W)",
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

    @staticmethod
    def _tier_of(current: float, t_high: float, t_normal: float) -> str:
        """Aktuelle Stufe aus dem Sollwert ableiten (high/normal/base)."""
        if current >= t_high - 0.5:
            return "high"
        if current >= t_normal - 0.5:
            return "normal"
        return "base"

    def _desired(self, o: dict, surplus: float, cur: str) -> str:
        """Gewünschte Stufe aus Roh-Überschuss + aktueller Stufe (Hysterese über cur).

        - aus base hoch erst ab Wiederanlauf-Schwelle (kein Rauschen-Flattern),
        - in normal/high gehalten, solange Überschuss >= Halte-Schwelle.

        WICHTIG (Hochstufe): Sie bleibt aktiv, solange Überschuss >= Halte – NICHT
        nur solange >= Hoch-Schwelle. Sonst würde die selbst-verbrauchende Hochstufe
        (Heizstab ~1500 W / Boost) ihren eigenen Überschuss „auffressen", den
        (bei 0 gekappten) Messwert unter die Hoch-Schwelle drücken und im 5-min-Takt
        pendeln. Drinbleiben bis der reale Überschuss wirklich weg ist (< Halte) und
        dann direkt auf Grund (kein 75->65-Zwischenschritt).
        """
        high = float(o.get(CONF_PV_HIGH, DEFAULT_PV_HIGH))
        reraise = float(o.get(CONF_PV_RERAISE_THRESHOLD, DEFAULT_PV_RERAISE_THRESHOLD))
        hold = float(o.get(CONF_PV_HOLD, DEFAULT_PV_HOLD))
        if cur == "base":
            return "high" if surplus >= high else ("normal" if surplus >= reraise else "base")
        if cur == "normal":
            return "high" if surplus >= high else ("normal" if surplus >= hold else "base")
        # cur == "high": Hysterese – drinbleiben, solange noch Überschuss da ist.
        return "high" if surplus >= hold else "base"

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
        if o.get(CONF_PV_MODE) != PV_MODE_COORDINATOR:
            self._reset()
            return

        surplus = state_float(self.hass, o.get(CONF_PV_SENSOR))
        if surplus is None:
            return

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
        water = float(data.get(REG_WATER_TEMP) or 0)
        t_high, t_normal, t_base = self._temps(o)

        # 1) Morgen-Start (fix, einmal/Tag): WW im ECO-Fenster anstoßen.
        morning = _parse_time(o.get(CONF_PV_MORNING_TIME, DEFAULT_PV_MORNING_TIME))
        if (o.get(CONF_PV_MORNING_ENABLED, DEFAULT_PV_MORNING_ENABLED)
                and now.time() >= morning and self._last_kick_day != now.date()):
            self._last_kick_day = now.date()
            if water < t_base and current < t_normal and self._start_allowed(o, running, now):
                target = int(min(max(int(t_normal), SET_TEMP_MIN), SET_TEMP_MAX))
                await coordinator.write_value(REG_SET_TEMP, target)
                _LOGGER.debug("PV: Morgen-Start Soll -> %d (Überschuss %.0f W)", target, surplus)
                self._announce(coordinator, target, surplus, up=True)
                return

        # 2) Stufenlogik aus Roh-Überschuss (Hysterese über cur) + Entprellung.
        cur = self._tier_of(current, t_high, t_normal)
        desired = self._desired(o, surplus, cur)
        if self._candidate != desired:
            self._candidate = desired
            self._since = now
            return
        debounce_s = o.get(CONF_PV_DEBOUNCE, DEFAULT_PV_DEBOUNCE) * 60
        if self._since is None or (now - self._since).total_seconds() < debounce_s:
            return

        target_temp = {"high": t_high, "normal": t_normal, "base": t_base}[desired]
        target = int(min(max(int(target_temp), SET_TEMP_MIN), SET_TEMP_MAX))
        if int(current) != target:
            if target < int(current):
                # Runter immer (kein Anti-Takt nötig).
                await coordinator.write_value(REG_SET_TEMP, target)
                _LOGGER.debug("PV: Soll %d -> %d (runter, Überschuss %.0f W)",
                              int(current), target, surplus)
                self._announce(coordinator, target, surplus, up=False)
            else:
                # Hoch nur bei High oder erlaubtem Wiederanlauf, Speicher unter Ziel
                # und Anti-Takt ok. Ausnahme: Heizstab-Dump (Hochstufe + ELEC) ist
                # kein Verdichterzyklus -> kein Anti-Takt, darf sofort hoch.
                up_ok = (desired == "high"
                         or o.get(CONF_PV_RERAISE_ENABLED, DEFAULT_PV_RERAISE_ENABLED))
                elec_dump = (desired == "high"
                             and o.get(CONF_PV_ESCALATION, PV_ESC_NONE) == PV_ESC_ELEC)
                if water < target and up_ok and (elec_dump or self._start_allowed(o, running, now)):
                    await coordinator.write_value(REG_SET_TEMP, target)
                    _LOGGER.debug("PV: Soll %d -> %d (hoch, Überschuss %.0f W, %s)",
                                  int(current), target, surplus,
                                  "WP läuft" if running else ("Heizstab-Dump" if elec_dump else "Stillstand ok"))
                    self._announce(coordinator, target, surplus, up=True)

        # Eskalation bei hohem Überschuss – greift in der Hochstufe AUCH bei stehender
        # WP (Boost startet WP+Heizstab, ELEC dumpt in den Heizstab); idempotent.
        await self._apply_escalation(coordinator, o, data, desired == "high", surplus)

    async def _apply_escalation(self, coordinator, o, data, high: bool, surplus: float) -> None:
        """Eskalation bei hohem Überschuss – genau EINE Option (Boost ODER ELEC ODER
        keine), daher kein Widerspruch möglich. Aufräumen (Boost-Bit löschen / Modus
        zurücksetzen) geschieht, sobald die jeweilige Option nicht (mehr) aktiv ist –
        auch beim Umschalten zwischen den Optionen.
        """
        choice = o.get(CONF_PV_ESCALATION, PV_ESC_NONE)
        want_boost = high and choice == PV_ESC_BOOST
        want_elec = high and choice == PV_ESC_ELEC

        # Boost-Bit (Reg 2)
        func = data.get(REG_FUNCTION)
        if func is not None:
            on = bool(func & BIT_BOOST)
            if want_boost and not on:
                await coordinator.write_value(REG_FUNCTION, func | BIT_BOOST)
                self._boost_applied = True
                _LOGGER.debug("PV: Boost an (Überschuss %.0f W)", surplus)
            elif not want_boost and on and self._boost_applied:
                await coordinator.write_value(REG_FUNCTION, func & ~BIT_BOOST)
                self._boost_applied = False
                _LOGGER.debug("PV: Boost aus")

        # Heizstab via Modus ELEC (Reg 1)
        mode = data.get(REG_MODE)
        if mode is not None:
            if want_elec and mode != MODE_ELEC:
                self._prev_mode = mode
                await coordinator.write_value(REG_MODE, MODE_ELEC)
                _LOGGER.debug("PV: Modus -> ELEC (Heizstab, Überschuss %.0f W)", surplus)
            elif not want_elec and mode == MODE_ELEC and self._prev_mode is not None:
                await coordinator.write_value(REG_MODE, self._prev_mode)
                _LOGGER.debug("PV: Modus zurück -> %s", self._prev_mode)
                self._prev_mode = None
