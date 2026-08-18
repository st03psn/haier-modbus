"""Notfall-Nachheizung: schaltet bei kritisch niedriger Warmwassertemperatur
vorübergehend von ECO auf AUTO (Default) oder ELEC, damit sofort (komfortgeführt)
geheizt wird – unabhängig vom ECO-Zeitfenster. Bei Erholung zurück auf ECO.

Hintergrund: ECO heizt nur in Zeitfenstern; wird tagsüber viel Wasser gezogen,
kann es vor dem nächsten Fenster ausgehen. AUTO hat WP-Vorrang und heizt
jederzeit. Den ECO-Zeitplan liefert Modbus nicht, daher eine Temperatur-Sicherung.

**Eskalationsmodus (``CONF_EMERGENCY_MODE``, seit v1.16.0):** ``auto`` (Default,
bisheriges Verhalten) oder ``elec`` – nur Heizstab, schnellste Aufheizung. ELEC ist damit
seit v1.16.0 ausschließlich hier verortet, nicht mehr Teil der PV-Eskalation in ``pv.py``:
Reg 1 ist ein *Wert* (0 AUTO · 1 ECO · 2 ELEC · 3 VAC), kein Bitfeld – "ELEC als Bit
schalten" existiert nicht, es bleibt ein echter Moduswechsel.

Die Rück-Schwelle ``recover`` wird nie unter den aktuellen Sollwert (Reg 6)
gelegt: Läge sie darunter (z. B. recover 48 °C bei Sollwert 50/60 °C), gäbe die
Notheizung schon *vor* dem Sollwert von AUTO/ELEC an ECO zurück – und zwar genau in
die ECO-Totzone (knapp unter dem Sollwert, aber über der Wiedereinschaltschwelle
des Geräts). ECO springt dann trotz offenem Zeitfenster nicht wieder an und die
Zieltemperatur wird nie erreicht. Effektiv wird daher bis mindestens zum Sollwert
nachgeheizt (``max(recover, Sollwert)``).
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import (
    CONF_EMERGENCY_CRITICAL,
    CONF_EMERGENCY_ENABLED,
    CONF_EMERGENCY_MODE,
    CONF_EMERGENCY_RECOVER,
    DEFAULT_EMERGENCY_CRITICAL,
    DEFAULT_EMERGENCY_MODE,
    DEFAULT_EMERGENCY_RECOVER,
    EMERGENCY_MODE_ELEC,
    MODE_AUTO,
    MODE_ECO,
    MODE_ELEC,
    REG_MODE,
    REG_SET_TEMP,
    REG_WATER_TEMP,
)

_LOGGER = logging.getLogger(__name__)


class EmergencyController:
    """ECO->AUTO/ELEC bei kritischer Temperatur, zurück bei Erholung (zustandsbehaftet)."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._forced = False  # haben wir ECO->AUTO/ELEC geschaltet?

    @property
    def active(self) -> bool:
        """True, solange die Notheizung gerade selbst forciert hat (besitzt den Modus).

        Von ``pv.py`` genutzt, um beim Modus (nicht beim Sollwert – den besitzt die
        Notheizung nicht) zurückzutreten, solange sie aktiv ist (Rangfolge AP4).
        """
        return self._forced

    async def async_evaluate(self, coordinator, data: dict[int, int]) -> None:
        o = coordinator.entry.options
        if not o.get(CONF_EMERGENCY_ENABLED, False):
            self._forced = False
            return

        # Läuft die Legionellen-Desinfektion, heizt sie ohnehin auf 65 °C und
        # besitzt den Modus – die Notheizung tritt zurück (kein Modus-Konflikt).
        if coordinator.legionella.active:
            self._forced = False
            return

        mode = data.get(REG_MODE)
        water = data.get(REG_WATER_TEMP)
        if mode is None or water is None:
            return

        critical = o.get(CONF_EMERGENCY_CRITICAL, DEFAULT_EMERGENCY_CRITICAL)
        recover = o.get(CONF_EMERGENCY_RECOVER, DEFAULT_EMERGENCY_RECOVER)
        forced_mode = (
            MODE_ELEC if o.get(CONF_EMERGENCY_MODE, DEFAULT_EMERGENCY_MODE) == EMERGENCY_MODE_ELEC
            else MODE_AUTO
        )

        # Nie unter dem aktuellen Sollwert (Reg 6) auf ECO zurückfallen, sonst
        # endet die Notheizung in der ECO-Totzone vor der Zieltemperatur und die
        # WP bleibt trotz offenem ECO-Fenster aus (Ziel nie erreicht).
        setpoint = data.get(REG_SET_TEMP)
        recover_at = recover if setpoint is None else max(recover, setpoint)

        # ``_forced`` ist der Besitz-Merker: nur wer forciert hat, darf zurückschalten.
        # Er wird deshalb ausschließlich nach einem **erfolgreichen** Schreibzugriff
        # umgelegt. Andernfalls liefen Merker und Gerät auseinander – im schlimmsten
        # Fall bliebe das Gerät in AUTO/ELEC stehen, ohne dass sich noch jemand dafür
        # zuständig fühlt. Ein Fehlversuch wiederholt sich beim nächsten Poll von selbst,
        # weil die Bedingungen unverändert gelten.
        if not self._forced:
            if mode == MODE_ECO and water <= critical:
                if await coordinator.write_value(REG_MODE, forced_mode):
                    self._forced = True
                    _LOGGER.info(
                        "Notfall-Nachheizung: ECO -> %s (Wasser %.0f °C ≤ %s)",
                        "ELEC" if forced_mode == MODE_ELEC else "AUTO", water, critical,
                    )
        else:
            if mode != forced_mode:
                # Nutzer/Logik hat den Modus geändert -> nicht mehr unsere Sache.
                self._forced = False
            elif water >= recover_at:
                if await coordinator.write_value(REG_MODE, MODE_ECO):
                    self._forced = False
                    _LOGGER.info(
                        "Notfall-Nachheizung beendet: %s -> ECO (Wasser %.0f °C ≥ %s)",
                        "ELEC" if forced_mode == MODE_ELEC else "AUTO", water, recover_at,
                    )
