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
from homeassistant.helpers.storage import Store

from .const import (
    CONF_EMERGENCY_CRITICAL,
    CONF_EMERGENCY_ENABLED,
    CONF_EMERGENCY_MODE,
    CONF_EMERGENCY_RECOVER,
    DEFAULT_EMERGENCY_CRITICAL,
    DEFAULT_EMERGENCY_MODE,
    DEFAULT_EMERGENCY_RECOVER,
    DOMAIN,
    EMERGENCY_MODE_ELEC,
    MODE_AUTO,
    MODE_ECO,
    MODE_ELEC,
    REG_MODE,
    REG_SET_TEMP,
    REG_WATER_TEMP,
)

_LOGGER = logging.getLogger(__name__)

_STORAGE_VERSION = 1


class EmergencyController:
    """ECO->AUTO/ELEC bei kritischer Temperatur, zurück bei Erholung (zustandsbehaftet)."""

    def __init__(self, hass: HomeAssistant, store_factory=Store) -> None:
        self.hass = hass
        self._store_factory = store_factory
        self._forced = False  # haben wir ECO->AUTO/ELEC geschaltet?
        self._store: Store | None = None
        self._loaded = False
        # Live-Status (vom Diagnose-Sensor gelesen, T4/C12): bislang war ``_forced``
        # nirgends sichtbar – ein in ELEC hängendes Gerät (K1) fiel nur an der
        # Stromrechnung auf.
        self.status: dict = {"state": "idle", "forced_mode": None, "water": None}

    async def _ensure_loaded(self, coordinator) -> None:
        """Besitz-Merker aus der Statusdatei laden (K1): ohne das überlebt ein
        forcierter Lauf keinen HA-Neustart – Reg 1 bleibt dann dauerhaft in
        AUTO/ELEC hängen, weil weder der Arm-Zweig (verlangt MODE_ECO) noch der
        Rückgabe-Zweig (verlangt ``_forced``) je wieder greift."""
        if self._loaded:
            return
        self._loaded = True
        self._store = self._store_factory(
            self.hass, _STORAGE_VERSION, f"{DOMAIN}_emergency_{coordinator.entry.entry_id}"
        )
        try:
            data = await self._store.async_load()
        except Exception:  # noqa: BLE001
            data = None
        if data:
            self._forced = bool(data.get("forced", False))

    async def _save_store(self) -> None:
        if self._store is None:
            return
        await self._store.async_save({"forced": self._forced})

    @property
    def active(self) -> bool:
        """True, solange die Notheizung gerade selbst forciert hat (besitzt den Modus).

        Von ``pv.py`` genutzt, um beim Modus (nicht beim Sollwert – den besitzt die
        Notheizung nicht) zurückzutreten, solange sie aktiv ist (Rangfolge AP4).
        """
        return self._forced

    def _set_status(self, state, forced_mode=None, water=None) -> None:
        self.status = {
            "state": state,
            "forced_mode": forced_mode,
            "water": None if water is None else round(float(water), 1),
        }

    async def async_evaluate(self, coordinator, data: dict[int, int]) -> None:
        o = coordinator.entry.options
        await self._ensure_loaded(coordinator)

        if not o.get(CONF_EMERGENCY_ENABLED, False):
            if self._forced:
                # K5: Abschalten mitten in einem forcierten Lauf darf das Gerät nicht
                # in AUTO/ELEC zurücklassen – Vorlage ist der ``_restore()``-Handshake
                # in legionella.py (inkl. Retry im Folgepoll bei Schreibfehler statt
                # den Merker blind zu löschen).
                if not await coordinator.write_value(REG_MODE, MODE_ECO):
                    self._set_status("forced")
                    return
                self._forced = False
                await self._save_store()
            self._set_status("disabled")
            return

        # Läuft die Legionellen-Desinfektion, heizt sie ohnehin auf 65 °C und
        # besitzt den Modus – die Notheizung tritt zurück (kein Modus-Konflikt).
        if coordinator.legionella.active:
            if self._forced:
                self._forced = False
                await self._save_store()
            self._set_status("idle")
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
                    await self._save_store()
                    _LOGGER.info(
                        "Notfall-Nachheizung: ECO -> %s (Wasser %.0f °C ≤ %s)",
                        "ELEC" if forced_mode == MODE_ELEC else "AUTO", water, critical,
                    )
        else:
            if mode != forced_mode:
                # Nutzer/Logik hat den Modus geändert -> nicht mehr unsere Sache.
                self._forced = False
                await self._save_store()
            elif water >= recover_at:
                if await coordinator.write_value(REG_MODE, MODE_ECO):
                    self._forced = False
                    await self._save_store()
                    _LOGGER.info(
                        "Notfall-Nachheizung beendet: %s -> ECO (Wasser %.0f °C ≥ %s)",
                        "ELEC" if forced_mode == MODE_ELEC else "AUTO", water, recover_at,
                    )

        self._set_status(
            "forced" if self._forced else "idle",
            forced_mode="ELEC" if forced_mode == MODE_ELEC else "AUTO",
            water=water,
        )
