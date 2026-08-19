"""Legionellen-Schutz: periodische thermische Desinfektion (Watchdog-Prinzip).

Statt Duschgewohnheiten zu „lernen", überwacht dieser Controller nur die eine
sicherheitsrelevante Größe: **wie lange ist die letzte vollständige Durchheizung
her?** Erreicht der Speicher nicht innerhalb des Intervalls (Default 7 Tage) am
*Boden* (``Tank unten``, Reg 9 – die kälteste Schicht) die Zieltemperatur, wird
ein Desinfektionslauf erzwungen.

Ablauf eines Laufs (kein Timeout/Abbruch – läuft, bis erreicht):
- Sollwert (Reg 6) temporär auf das Ziel (Default 65 °C) anheben.
- Bevorzugt im **ECO-Fenster** (Default 10–18 Uhr) mit Modus ECO mitheizen; da ECO
  am Sollwert träge ist, nach einer Anlaufzeit bzw. außerhalb des Fensters auf
  **AUTO** eskalieren, damit das Ziel *garantiert* erreicht wird.
- Erfolg = ``Tank unten`` hält die Boden-Schwelle (Default 60 °C) für die Haltezeit
  (Default 30 min). Erst dann Timer zurücksetzen und den vorherigen Sollwert/Modus
  wiederherstellen.

Selbst-Reset: Wird der Speicher aus beliebigem Grund (z. B. PV-Boost auf 65/75 °C)
ohnehin voll durchgeheizt, zählt das als Desinfektion – der Timer springt zurück
und es läuft kein Extra-Zyklus. Im Alltag mit täglicher Nutzung greift der Schutz
also kaum; er ist die Absicherung für Stagnation (Urlaub).

Solange ein Lauf aktiv ist, pausiert die PV-Sollwert-Regelung (sonst würde sie
gegen den 65-°C-Sollwert schreiben); nach dem Lauf übernimmt sie wieder normal.
"""

from __future__ import annotations

import logging
from datetime import time, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
import homeassistant.util.dt as dt_util

from .const import (
    CONF_LEGIONELLA_BOTTOM,
    CONF_LEGIONELLA_ENABLED,
    CONF_LEGIONELLA_HOLD,
    CONF_LEGIONELLA_INTERVAL,
    CONF_LEGIONELLA_TARGET,
    CONF_LEGIONELLA_WINDOW_END,
    CONF_LEGIONELLA_WINDOW_START,
    DEFAULT_LEGIONELLA_BOTTOM,
    DEFAULT_LEGIONELLA_HOLD,
    DEFAULT_LEGIONELLA_INTERVAL,
    DEFAULT_LEGIONELLA_TARGET,
    DEFAULT_LEGIONELLA_WINDOW_END,
    DEFAULT_LEGIONELLA_WINDOW_START,
    DOMAIN,
    MODE_AUTO,
    MODE_ECO,
    REG_MODE,
    REG_SET_TEMP,
    REG_TANK_BOTTOM,
    SET_TEMP_MIN,
    WP_MAX_TEMP,
)

_LOGGER = logging.getLogger(__name__)

_STORAGE_VERSION = 1
# Bevorzugt heizt der Lauf im ECO-Fenster mit ECO mit; kommt er dort nach dieser
# Anlaufzeit nicht ans Ziel (ECO ist am Sollwert träge), wird auf AUTO eskaliert,
# damit der Boden garantiert erreicht wird. Das ist kein Abbruch – der Lauf endet
# ausschließlich bei nachgewiesenem Erfolg.
_ESCALATE_AFTER_S = 90 * 60


def _parse_time(raw) -> time:
    """"HH:MM" / "HH:MM:SS" -> time; bei Unsinn Default 10:00."""
    try:
        parts = str(raw).split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return time(10, 0)


class LegionellaController:
    """Watchdog auf die letzte Volldurchheizung; erzwingt bei Bedarf 65 °C."""

    def __init__(self, hass: HomeAssistant, store_factory=Store) -> None:
        self.hass = hass
        self._store_factory = store_factory
        self.active = False                     # läuft gerade ein Desinfektionslauf?
        self._last_success = None               # datetime der letzten Volldurchheizung
        self._run_started = None                # datetime des aktuellen Laufs
        self._bottom_since = None               # seit wann hält Tank-unten das Ziel?
        self._releasing = False                 # Lauf fertig, warte auf Sollwert-Rückkehr
        self._saved_setpoint: int | None = None
        self._saved_mode: int | None = None
        self._store: Store | None = None
        self._loaded = False
        self.status: dict = {"state": "off"}

    async def _ensure_loaded(self, coordinator) -> None:
        """Watchdog-Datum UND laufenden Desinfektionslauf laden (K3).

        Ohne den zweiten Teil überlebt ein aktiver Lauf keinen HA-Neustart/Reload:
        ``_saved_setpoint``/``_saved_mode`` gehen verloren, ``_restore()`` wird nie
        aufgerufen, der Speicher bleibt auf dem 65-°C-Sollwert stehen (bei
        ``pv_mode: off``/``executor`` schreibt niemand zurück).
        """
        if self._loaded:
            return
        self._loaded = True
        self._store = self._store_factory(
            self.hass, _STORAGE_VERSION, f"{DOMAIN}_legionella_{coordinator.entry.entry_id}"
        )
        try:
            data = await self._store.async_load()
        except Exception:  # noqa: BLE001
            data = None
        if data:
            if data.get("last_success"):
                self._last_success = dt_util.parse_datetime(data["last_success"])
            self.active = bool(data.get("active", False))
            self._releasing = bool(data.get("releasing", False))
            if data.get("saved_setpoint") is not None:
                self._saved_setpoint = int(data["saved_setpoint"])
            if data.get("saved_mode") is not None:
                self._saved_mode = int(data["saved_mode"])
            if data.get("run_started"):
                self._run_started = dt_util.parse_datetime(data["run_started"])

    async def _save_store(self) -> None:
        if self._store is None:
            return
        await self._store.async_save({
            "last_success": self._last_success.isoformat() if self._last_success else None,
            "active": self.active,
            "releasing": self._releasing,
            "saved_setpoint": self._saved_setpoint,
            "saved_mode": self._saved_mode,
            "run_started": self._run_started.isoformat() if self._run_started else None,
        })

    async def _mark_success(self, when) -> None:
        self._last_success = when
        await self._save_store()

    def _in_window(self, o: dict, now) -> bool:
        start = _parse_time(o.get(CONF_LEGIONELLA_WINDOW_START, DEFAULT_LEGIONELLA_WINDOW_START))
        end = _parse_time(o.get(CONF_LEGIONELLA_WINDOW_END, DEFAULT_LEGIONELLA_WINDOW_END))
        t = now.time()
        if start <= end:
            return start <= t < end
        return t >= start or t < end   # über Mitternacht (falls jemand 22–06 setzt)

    def _start_ok(self, o: dict, now) -> bool:
        """Bevorzugt im ECO-Fenster starten; nie zur Unzeit einen Kaltstart – außer
        der Schutz ist deutlich überfällig (dann jederzeit, um ihn zu erzwingen)."""
        if self._in_window(o, now):
            return True
        if self._last_success is None:
            return False   # Erstschutz auf das nächste Fenster (≤ 24 h) warten
        interval = int(o.get(CONF_LEGIONELLA_INTERVAL, DEFAULT_LEGIONELLA_INTERVAL))
        return (now - self._last_success) >= timedelta(days=interval + 1)

    def _desired_mode(self, o: dict, now) -> int:
        """Im Fenster zunächst ECO (effizient mitheizen), danach/außerhalb AUTO."""
        if (self._in_window(o, now) and self._run_started is not None
                and (now - self._run_started).total_seconds() < _ESCALATE_AFTER_S):
            return MODE_ECO
        return MODE_AUTO

    async def _restore(self, coordinator) -> bool:
        """Vorherigen Sollwert/Modus wiederherstellen (idempotent).

        Gibt True zurück, wenn **beide** Schreibzugriffe durchgingen. Der Aufrufer gibt
        den Lauf erst dann frei – sonst bliebe der Speicher auf dem 65-°C-Sollwert
        stehen, und die PV-Leiter würde diesen fremden Sollwert als manuellen Eingriff
        werten und sich zurückziehen.
        """
        ok = True
        if self._saved_mode is not None:
            ok &= await coordinator.write_value(REG_MODE, int(self._saved_mode))
        if self._saved_setpoint is not None:
            ok &= await coordinator.write_value(REG_SET_TEMP, int(self._saved_setpoint))
        return bool(ok)

    async def async_evaluate(self, coordinator, data: dict[int, int], now=None) -> None:
        o = coordinator.entry.options
        await self._ensure_loaded(coordinator)

        if not o.get(CONF_LEGIONELLA_ENABLED, False):
            if self.active:
                # Feature während eines Laufs abgeschaltet -> sauber freigeben. Gelingt
                # das Zurückschreiben nicht, bleibt der Lauf als aktiv markiert, damit der
                # nächste Poll es erneut versucht – dasselbe Prinzip wie beim
                # ``_releasing``-Handshake weiter unten. Den Speicher auf 65 °C stehen zu
                # lassen wäre die schlechtere Alternative.
                if not await self._restore(coordinator):
                    return  # Status bleibt "running" – der Lauf ist noch nicht freigegeben
            self.active = False
            self._releasing = False
            self._run_started = None
            self._bottom_since = None
            self._saved_setpoint = None
            self._saved_mode = None
            await self._save_store()
            self.status = {"state": "off"}
            return

        now = now or dt_util.now()
        interval = int(o.get(CONF_LEGIONELLA_INTERVAL, DEFAULT_LEGIONELLA_INTERVAL))
        target = _clamp(int(o.get(CONF_LEGIONELLA_TARGET, DEFAULT_LEGIONELLA_TARGET)))
        bottom_min = int(o.get(CONF_LEGIONELLA_BOTTOM, DEFAULT_LEGIONELLA_BOTTOM))
        hold_s = int(o.get(CONF_LEGIONELLA_HOLD, DEFAULT_LEGIONELLA_HOLD)) * 60

        bottom = data.get(REG_TANK_BOTTOM)
        mode = data.get(REG_MODE)
        setpoint = data.get(REG_SET_TEMP)
        if bottom is None or mode is None or setpoint is None:
            return  # unvollständige Daten -> nächster Zyklus

        # Abschluss-Handshake: Lauf fertig, aber die PV-Regelung bleibt pausiert, bis
        # der Sollwert im Register wieder auf dem Ausgangswert steht (sonst würde sie
        # den 65-°C-Sollwert im veralteten Poll als „manuellen Eingriff" werten).
        if self._releasing:
            if int(setpoint) == int(self._saved_setpoint or setpoint):
                self.active = False
                self._releasing = False
                self._saved_setpoint = None
                self._saved_mode = None
                self._run_started = None
                await self._save_store()
            else:
                await self._restore(coordinator)
            self._snapshot("idle" if not self.active else "running", now, bottom, target, interval)
            return

        due = (
            self._last_success is None
            or (now - self._last_success) >= timedelta(days=interval)
        )

        # Verifikation (aktiv wie passiv): hält Tank-unten das Ziel lange genug?
        if bottom >= bottom_min:
            if self._bottom_since is None:
                self._bottom_since = now
            held = (now - self._bottom_since).total_seconds() >= hold_s
        else:
            self._bottom_since = None
            held = False

        # Erfolg nur werten, wenn ein Lauf läuft oder der Schutz fällig ist – so
        # löst ein dauerhaft heißer Speicher (nach Erfolg) nicht bei jedem Poll
        # erneut einen Timer-Reset aus.
        if held and (self.active or due):
            await self._mark_success(now)
            self._bottom_since = None
            if self.active:
                _LOGGER.info(
                    "Legionellen-Desinfektion erreicht: Tank unten ≥ %d °C für %d min gehalten",
                    bottom_min, hold_s // 60,
                )
                await self._restore(coordinator)
                self._releasing = True     # Freigabe erst, wenn Sollwert zurückgelesen
                await self._save_store()
            self._snapshot("running" if self.active else "idle", now, bottom, target, interval)
            return

        if not self.active and due and self._start_ok(o, now):
            self.active = True
            self._run_started = now
            self._saved_setpoint = int(setpoint)
            # K4: Läuft die Notheizung gerade forciert (AUTO/ELEC), ist DAS nicht der
            # wahre Ausgangszustand, sondern ihr eigener Eingriff. Würden wir den
            # rohen Registerwert sichern, käme beim Restore genau dieser erzwungene
            # Modus zurück – die Notheizung hat ihren Besitz aber schon beim
            # Zurücktreten für diesen Lauf aufgegeben (``emergency.py``: tritt
            # zurück, sobald ``legionella.active`` gilt) und würde ihn nie wieder
            # übernehmen (Reg 1 steht dann auf AUTO/ELEC, der Arm-Zweig verlangt
            # aber MODE_ECO). Der wahre Ausgangszustand ist ECO.
            emergency = getattr(coordinator, "emergency", None)
            self._saved_mode = (
                MODE_ECO if emergency is not None and emergency.active else int(mode)
            )
            await self._save_store()
            _LOGGER.info(
                "Legionellen-Desinfektion gestartet (Ziel %d °C, Tank unten ≥ %d °C)",
                target, bottom_min,
            )

        if self.active:
            if int(setpoint) != target:
                await coordinator.write_value(REG_SET_TEMP, target)
            want_mode = self._desired_mode(o, now)
            if int(mode) != want_mode:
                await coordinator.write_value(REG_MODE, want_mode)
            self._snapshot(
                "holding" if bottom >= bottom_min else "running",
                now, bottom, target, interval, want_mode,
            )
        else:
            self._snapshot("due" if due else "idle", now, bottom, target, interval)

    def _snapshot(self, state, now, bottom, target, interval, mode=None) -> None:
        last = self._last_success
        days = None if last is None else round((now - last).total_seconds() / 86400, 1)
        nxt = None if last is None else (last + timedelta(days=interval))
        self.status = {
            "state": state,
            "last_success": None if last is None else last.isoformat(),
            "days_since": days,
            "next_due": None if nxt is None else nxt.isoformat(),
            "tank_bottom": bottom,
            "target": target,
            "mode": mode,
        }


def _clamp(value: int) -> int:
    # W3: Verdichtergrenze, nicht die Registergrenze (75) - der Lauf eskaliert auf
    # AUTO (reine WP), ein Ziel oberhalb WP_MAX_TEMP wäre dort nie erreichbar.
    return min(max(value, SET_TEMP_MIN), WP_MAX_TEMP)
