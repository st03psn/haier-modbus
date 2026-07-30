"""Notfall-Nachheizung: schaltet bei kritisch niedriger Warmwassertemperatur
vorübergehend von ECO auf AUTO, damit sofort (komfortgeführt) geheizt wird –
unabhängig vom ECO-Zeitfenster. Bei Erholung zurück auf ECO.

Hintergrund: ECO heizt nur in Zeitfenstern; wird tagsüber viel Wasser gezogen,
kann es vor dem nächsten Fenster ausgehen. AUTO hat WP-Vorrang und heizt
jederzeit. Den ECO-Zeitplan liefert Modbus nicht, daher eine Temperatur-Sicherung.

Die Rück-Schwelle ``recover`` wird nie unter den aktuellen Sollwert (Reg 6)
gelegt: Läge sie darunter (z. B. recover 48 °C bei Sollwert 50/60 °C), gäbe die
Notheizung schon *vor* dem Sollwert von AUTO an ECO zurück – und zwar genau in
die ECO-Totzone (knapp unter dem Sollwert, aber über der Wiedereinschaltschwelle
des Geräts). ECO springt dann trotz offenem Zeitfenster nicht wieder an und die
Zieltemperatur wird nie erreicht. Effektiv wird daher bis mindestens zum Sollwert
in AUTO nachgeheizt (``max(recover, Sollwert)``).
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import (
    CONF_EMERGENCY_CRITICAL,
    CONF_EMERGENCY_ENABLED,
    CONF_EMERGENCY_RECOVER,
    DEFAULT_EMERGENCY_CRITICAL,
    DEFAULT_EMERGENCY_RECOVER,
    MODE_AUTO,
    MODE_ECO,
    REG_MODE,
    REG_SET_TEMP,
    REG_WATER_TEMP,
)

_LOGGER = logging.getLogger(__name__)


class EmergencyController:
    """ECO->AUTO bei kritischer Temperatur, zurück bei Erholung (zustandsbehaftet)."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._forced = False  # haben wir ECO->AUTO geschaltet?

    async def async_evaluate(self, coordinator, data: dict[int, int]) -> None:
        o = coordinator.entry.options
        if not o.get(CONF_EMERGENCY_ENABLED, False):
            self._forced = False
            return

        mode = data.get(REG_MODE)
        water = data.get(REG_WATER_TEMP)
        if mode is None or water is None:
            return

        critical = o.get(CONF_EMERGENCY_CRITICAL, DEFAULT_EMERGENCY_CRITICAL)
        recover = o.get(CONF_EMERGENCY_RECOVER, DEFAULT_EMERGENCY_RECOVER)

        # Nie unter dem aktuellen Sollwert (Reg 6) auf ECO zurückfallen, sonst
        # endet die Notheizung in der ECO-Totzone vor der Zieltemperatur und die
        # WP bleibt trotz offenem ECO-Fenster aus (Ziel nie erreicht).
        setpoint = data.get(REG_SET_TEMP)
        recover_at = recover if setpoint is None else max(recover, setpoint)

        if not self._forced:
            if mode == MODE_ECO and water <= critical:
                await coordinator.write_value(REG_MODE, MODE_AUTO)
                self._forced = True
                _LOGGER.info(
                    "Notfall-Nachheizung: ECO -> AUTO (Wasser %.0f °C ≤ %s)", water, critical
                )
        else:
            if mode != MODE_AUTO:
                # Nutzer/Logik hat den Modus geändert -> nicht mehr unsere Sache.
                self._forced = False
            elif water >= recover_at:
                await coordinator.write_value(REG_MODE, MODE_ECO)
                self._forced = False
                _LOGGER.info(
                    "Notfall-Nachheizung beendet: AUTO -> ECO (Wasser %.0f °C ≥ %s)",
                    water, recover_at,
                )
