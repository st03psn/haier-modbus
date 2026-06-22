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
    }


async def _aligned_consumption(
    hass: HomeAssistant, heat_ids: list[str], elec_ids: list[str], start, end
) -> tuple[float | None, float | None]:
    """Wärme- und Strom-Verbrauch im Fenster [start, end], auf gemeinsames Fenster ausgerichtet.

    Nutzt die reset-bereinigte ``sum`` der Langzeitstatistik. Damit Zähler und
    Wärme denselben Zeitraum abdecken, wird als gemeinsamer Start der *späteste*
    erste Datenpunkt aller Quellen verwendet (also „ab dem auch Wärme verfügbar
    war"). Gibt (None, None) zurück, wenn nicht alle Quellen Daten haben.
    """
    if not heat_ids or not elec_ids:
        return None, None
    all_ids = [*heat_ids, *elec_ids]
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
            set(all_ids),
            "hour",
            None,
            {"sum"},
        )
    except Exception:  # noqa: BLE001
        return None, None

    for sid in all_ids:
        if not stats.get(sid):
            return None, None

    aligned = max(stats[sid][0]["start"] for sid in all_ids)

    def consume(ids: list[str]) -> float | None:
        total = 0.0
        for sid in ids:
            base = next((r.get("sum") for r in stats[sid] if r["start"] >= aligned), None)
            last = stats[sid][-1].get("sum")
            if base is None or last is None:
                return None
            total += last - base
        return total

    heat = consume(heat_ids)
    elec = consume(elec_ids)
    if heat is None or elec is None:
        return None, None
    return max(heat, 0.0), max(elec, 0.0)


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
        self, hass: HomeAssistant, heat_ids: list[str], elec_ids: list[str]
    ) -> bool:
        """Einmalig Monats-/Jahres-Eimer aus der Langzeitstatistik vorbefüllen.

        Liefert True, wenn geseedet (oder bereits geseedet) wurde, sonst False
        (z. B. noch keine Statistik verfügbar) – dann kann es später erneut
        versucht werden. Atomar: nur wenn alle vier Fenster ermittelbar sind.
        """
        if self._data is None:
            await self.async_load()
        if self._data.get("seeded"):
            return True

        now = dt_util.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

        mh, me = await _aligned_consumption(hass, heat_ids, elec_ids, month_start, now)
        yh, ye = await _aligned_consumption(hass, heat_ids, elec_ids, year_start, now)
        if None in (mh, me, yh, ye):
            return False

        d = self._data
        d["month_key"] = now.strftime("%Y-%m")
        d["year_key"] = now.strftime("%Y")
        d["month_heat"], d["month_elec"] = max(mh, 0.0), max(me, 0.0)
        d["year_heat"], d["year_elec"] = max(yh, 0.0), max(ye, 0.0)
        d["seeded"] = True
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
        """period: 'month' | 'year' (JAZ)."""
        h = self._g(f"{period}_heat")
        e = self._g(f"{period}_elec")
        return round(h / e, 2) if h and e else None

    def history(self) -> dict:
        """Abgeschlossene Jahre: {'2026': {'heat','elec','cop'}, ...}."""
        return dict((self._data or {}).get("history", {}))

    def previous_year_cop(self) -> float | None:
        """JAZ des zuletzt abgeschlossenen Jahres."""
        hist = (self._data or {}).get("history", {})
        if not hist:
            return None
        return hist[max(hist)].get("cop")  # max key = jüngstes Jahr (YYYY)
