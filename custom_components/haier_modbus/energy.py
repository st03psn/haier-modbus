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
# Erhöhen, um bestehende Installationen einmalig neu zu seeden (Logikwechsel).
SEED_VERSION = 3


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
        "totals_seeded_heat": False,
        "totals_seeded_elec": False,
        "month_key": None,
        "year_key": None,
        "month_heat": 0.0,
        "month_elec": 0.0,
        "year_heat": 0.0,
        "year_elec": 0.0,
        "seeded": False,
        "history": {},
        "history_month": {},
    }


async def consumption_since(
    hass: HomeAssistant, stat_ids: list[str], start, end
) -> float | None:
    """Verbrauch/Erzeugung im Fenster [start, end] aus der Langzeitstatistik.

    Eine Quelle (oder Summe mehrerer), reset-bereinigt über die ``sum``.
    Für den „COP seit Bezugsdatum" – kein Alignment nötig, fester Start.
    """
    ids = [s for s in stat_ids if s]
    if not ids:
        return None
    try:
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import (
            statistics_during_period,
        )

        stats = await get_instance(hass).async_add_executor_job(
            statistics_during_period,
            hass,
            start,
            end,
            set(ids),
            "hour",
            None,
            {"sum"},
        )
    except Exception:  # noqa: BLE001
        return None

    total = 0.0
    for sid in ids:
        rows = stats.get(sid)
        if not rows:
            return None
        first = rows[0].get("sum")
        last = rows[-1].get("sum")
        if first is None or last is None:
            return None
        total += last - first
    return total


class EnergyAccumulator:
    """Akkumuliert Wärme/Strom in Monats-, Jahres- und Gesamt-Eimer."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry_id}.energy")
        self._data: dict | None = None
        self._dirty = False

    @property
    def loaded(self) -> bool:
        return self._data is not None

    @property
    def needs_seed(self) -> bool:
        """True, solange die Monats-/Jahres-Eimer (für die aktuelle Logik) ungeseedet sind."""
        return (self._data or {}).get("seed_version") != SEED_VERSION

    async def async_load(self) -> None:
        self._data = await self._store.async_load() or _empty()

    def _roll(self, now) -> None:
        d = self._data
        mkey = now.strftime("%Y-%m")
        ykey = now.strftime("%Y")
        if d["month_key"] != mkey:
            # Abgeschlossenen Monat archivieren (vor dem Reset), max. 36 behalten.
            if d["month_key"] is not None and d["month_heat"] > 0 and d["month_elec"] > 0:
                hm = d.setdefault("history_month", {})
                hm[d["month_key"]] = {
                    "heat": round(d["month_heat"], 3),
                    "elec": round(d["month_elec"], 3),
                    "cop": round(d["month_heat"] / d["month_elec"], 2),
                }
                for old in sorted(hm)[:-36]:
                    del hm[old]
            d["month_key"] = mkey
            d["month_heat"] = 0.0
            d["month_elec"] = 0.0
        if d["year_key"] != ykey:
            # Abgeschlossenes Jahr archivieren (vor dem Reset), sofern sinnvoll.
            if d["year_key"] is not None and d["year_heat"] > 0 and d["year_elec"] > 0:
                d.setdefault("history", {})[d["year_key"]] = {
                    "heat": round(d["year_heat"], 3),
                    "elec": round(d["year_elec"], 3),
                    "cop": round(d["year_heat"] / d["year_elec"], 2),
                }
            d["year_key"] = ykey
            d["year_heat"] = 0.0
            d["year_elec"] = 0.0

    def update(self, heat: float | None, elec: float | None) -> None:
        if self._data is None:
            self._data = _empty()
        d = self._data
        self._roll(dt_util.now())
        if heat is not None:
            if not d.get("totals_seeded_heat"):
                # Gesamt-Sensor mit aktuellem Quellenstand starten (nicht bei 0).
                d["total_heat"] = heat
                d["totals_seeded_heat"] = True
                d["prev_heat"] = heat
            else:
                dh = _delta(d["prev_heat"], heat)
                d["prev_heat"] = heat
                d["month_heat"] += dh
                d["year_heat"] += dh
                d["total_heat"] += dh
        if elec is not None:
            if not d.get("totals_seeded_elec"):
                d["total_elec"] = elec
                d["totals_seeded_elec"] = True
                d["prev_elec"] = elec
            else:
                de = _delta(d["prev_elec"], elec)
                d["prev_elec"] = elec
                d["month_elec"] += de
                d["year_elec"] += de
                d["total_elec"] += de
        self._dirty = True

    async def async_seed(
        self,
        month_heat: float,
        month_elec: float,
        year_heat: float,
        year_elec: float,
    ) -> bool:
        """Monats-/Jahres-Eimer mit vorberechneten Kalenderwerten vorbefüllen.

        Die Werte stammen aus autoritativen Quellen (Gerätemonats-/Jahres-
        register bzw. externe Kalender-Statistik), die den jeweiligen
        Kalenderzeitraum *direkt* abdecken – ohne fragiles Fenster-Alignment.
        Wird je ``SEED_VERSION`` genau einmal angewandt; danach übernimmt die
        laufende Delta-Akkumulation. Liefert True, wenn geseedet (oder schon
        auf aktueller Version geseedet) wurde.
        """
        if self._data is None:
            await self.async_load()
        if not self.needs_seed:
            return True

        now = dt_util.now()
        d = self._data
        d["month_key"] = now.strftime("%Y-%m")
        d["year_key"] = now.strftime("%Y")
        d["month_heat"], d["month_elec"] = max(month_heat, 0.0), max(month_elec, 0.0)
        d["year_heat"], d["year_elec"] = max(year_heat, 0.0), max(year_elec, 0.0)
        d["seeded"] = True
        d["seed_version"] = SEED_VERSION
        self._dirty = True
        await self.async_save()
        return True

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
        """period: 'month' | 'year' (JAZ). None bei unplausiblen Werten."""
        h = self._g(f"{period}_heat")
        e = self._g(f"{period}_elec")
        if not h or not e:
            return None
        ratio = h / e
        # Sanity: physikalisch unmögliche COP (Seeding-/Daten-Edgecases) ausblenden.
        if ratio <= 0 or ratio > 20:
            return None
        return round(ratio, 2)

    def history(self) -> dict:
        """Abgeschlossene Jahre: {'2026': {'heat','elec','cop'}, ...}."""
        return dict((self._data or {}).get("history", {}))

    def month_history(self) -> dict:
        """Abgeschlossene Monate: {'2026-06': {'heat','elec','cop'}, ...}."""
        return dict((self._data or {}).get("history_month", {}))

    def previous_year_cop(self) -> float | None:
        """JAZ des zuletzt abgeschlossenen Jahres."""
        hist = (self._data or {}).get("history", {})
        if not hist:
            return None
        return hist[max(hist)].get("cop")  # max key = jüngstes Jahr (YYYY)
