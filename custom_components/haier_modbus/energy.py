"""Kalender-ausgerichtete Energie-/COP-Akkumulation (utility_meter-Logik intern).

Löst das Problem unterschiedlicher Reset-Fenster von Strom- und Wärmeregister:
Beide Größen werden in HA-kontrollierte Monats- und Jahres-Eimer akkumuliert,
die gemeinsam zum Kalenderwechsel zurücksetzen. Quell-Resets (ein Register
springt zwischendurch auf 0) werden – wie bei ``utility_meter`` – über positive
Deltas abgefangen, sodass Zähler/Wärmemenge nicht mehr auseinanderlaufen.

Zusätzlich werden monotone Gesamt-Totale geführt; diese eignen sich als
``total_increasing``-Energiesensoren fürs Energie-Dashboard (Verbrauchs-/
Erzeugungskurven mit automatischer Tages-/Monats-/Jahres-Aufschlüsselung).
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
import homeassistant.util.dt as dt_util

from .const import DOMAIN

STORE_VERSION = 1


def _delta(prev: float | None, cur: float | None) -> float:
    """Positives Delta zweier kumulativer Messwerte; Quell-Reset -> cur."""
    if prev is None or cur is None:
        return 0.0
    if cur < prev:  # Quell-Reset (Register auf 0 gesprungen)
        return max(cur, 0.0)
    return cur - prev


def state_float(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Zustand einer Entität als float, sonst None."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", "", None):
        return None
    try:
        return float(state.state)
    except (ValueError, TypeError):
        return None


def _empty() -> dict:
    return {
        "prev_heat": None,
        "prev_elec": None,
        "total_heat": 0.0,
        "total_elec": 0.0,
        "month_key": None,
        "year_key": None,
        "month_heat": 0.0,
        "month_elec": 0.0,
        "year_heat": 0.0,
        "year_elec": 0.0,
    }


class EnergyAccumulator:
    """Akkumuliert Wärme/Strom in Monats-, Jahres- und Gesamt-Eimer."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry_id}.energy")
        self._data: dict | None = None
        self._dirty = False

    @property
    def loaded(self) -> bool:
        return self._data is not None

    async def async_load(self) -> None:
        self._data = await self._store.async_load() or _empty()

    def _roll(self, now) -> None:
        d = self._data
        mkey = now.strftime("%Y-%m")
        ykey = now.strftime("%Y")
        if d["month_key"] != mkey:
            d["month_key"] = mkey
            d["month_heat"] = 0.0
            d["month_elec"] = 0.0
        if d["year_key"] != ykey:
            d["year_key"] = ykey
            d["year_heat"] = 0.0
            d["year_elec"] = 0.0

    def update(self, heat: float | None, elec: float | None) -> None:
        if self._data is None:
            self._data = _empty()
        d = self._data
        self._roll(dt_util.now())
        if heat is not None:
            dh = _delta(d["prev_heat"], heat)
            d["prev_heat"] = heat
            d["month_heat"] += dh
            d["year_heat"] += dh
            d["total_heat"] += dh
        if elec is not None:
            de = _delta(d["prev_elec"], elec)
            d["prev_elec"] = elec
            d["month_elec"] += de
            d["year_elec"] += de
            d["total_elec"] += de
        self._dirty = True

    async def async_save(self) -> None:
        if self._data is not None and self._dirty:
            await self._store.async_save(self._data)
            self._dirty = False

    # --- Zugriff für Sensoren -------------------------------------------------
    def _g(self, key: str) -> float:
        return (self._data or {}).get(key, 0.0)

    def value(self, key: str) -> float:
        """Akkumulierter kWh-Wert, z. B. 'total_heat', 'month_elec', 'year_heat'."""
        return round(self._g(key), 3)

    def cop(self, period: str) -> float | None:
        """period: 'month' | 'year' (JAZ)."""
        h = self._g(f"{period}_heat")
        e = self._g(f"{period}_elec")
        return round(h / e, 2) if h and e else None
