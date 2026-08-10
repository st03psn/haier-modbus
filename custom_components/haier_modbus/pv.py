"""Optionale PV-Überschuss-Steuerung (Coordinator-Modus) innerhalb der Integration.

Zwei **unabhängige Schichten**, geregelt nach rohem PV-Überschuss
(``sensor.pv_uberschuss_watt``, kappt bei 0):

**Schicht 1 — WP-Zyklus (Sollwert Normal 50 ↔ Erhöht 65):**
- **Morgen-Start (fix, 1×/Tag):** der einzige Kaltstart — zur Uhrzeit, wenn Wasser
  unter Normal liegt, Sollwert auf Erhöht -> WP startet im ECO-Fenster.
- **Anheben Normal->Erhöht nur bei LAUFENDER WP** (Piggyback) + Überschuss ≥ Halte-Puffer.
  Kein Tages-Kaltstart -> kein Takten.
- **Halten** bei Erhöht solange Überschuss ≥ Halte ODER der Heizstab läuft.
- **Absenken** Erhöht->Normal, wenn Überschuss < Halte (entprellt) UND Heizstab aus.

**Schicht 2 — Heizstab (ad-hoc Zusatz, stoppt NIE die WP), ab Boost-Schwelle:**
- **Boost** (WP+Heizstab): nur bei **laufender** WP -> Sollwert Boost (75) + Boost-Bit.
- **ELEC** (nur Heizstab): nur bei **stehender** WP -> Modus ELEC + Sollwert Boost (75),
  Heizstab-Dump nach dem Tageszyklus. Ende -> Modus zurück (ECO) + Sollwert Normal.
- Fällt der Überschuss unter die Boost-Schwelle: nur der Heizstab geht weg (Sollwert
  Boost->Erhöht bei Boost bzw. ->Normal bei ELEC); die WP läuft unverändert weiter. Solange
  der Heizstab an ist, hält Schicht 1 die Erhöht-Stufe (kein fälschliches Absenken durch den
  Eigenverbrauch).

Nur im **Coordinator**-Modus aktiv; in **Aus**/**Executor** steigt ``async_evaluate``
sofort aus. Schreibzugriffe sind idempotent (nur bei Abweichung).
"""

from __future__ import annotations

import logging
from datetime import time, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
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

# Der Morgen-Start ist auf **einmal pro Kalendertag** begrenzt. Das „heute schon
# gefeuert"-Datum wird in einer Statusdatei (HA-Store) persistiert, damit ein
# HA-Neustart es nicht erneut auslöst (im RAM wäre es nach dem Neustart leer).
# Zusätzlich ein Zeitfenster ab der Morgen-Uhrzeit als Absicherung: war HA den
# ganzen Vormittag aus und kommt erst abends hoch, soll kein Abend-Kaltstart als
# „Morgen-Start" laufen.
_STORAGE_VERSION = 1
_MORNING_WINDOW_H = 3


def _parse_time(raw) -> time:
    """"HH:MM" / "HH:MM:SS" -> time; bei Unsinn Default 10:00."""
    try:
        parts = str(raw).split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return time(10, 0)


class PvController:
    """Coordinator-Modus: WP-Zyklus (Schicht 1) + Heizstab (Schicht 2) nach Überschuss."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        # Schicht 1 (WP-Zyklus): entprellter Ziel-Zustand (Normal/Erhöht).
        self._wp_target: float | None = None   # aktueller WP-Zyklus-Sollwert (Normal/Erhöht)
        self._wp_cand: float | None = None      # entprellter Kandidat
        self._wp_since = None
        # Schicht 2 (Heizstab): entprellter An/Aus-Zustand.
        self._heater_on = False
        self._heater_cand: bool | None = None
        self._heater_since = None
        self._boost_applied = False            # Boost-Bit von uns gesetzt?
        self._prev_mode: int | None = None     # Modus vor erzwungenem ELEC
        # Anti-Takt (nur noch für den Morgen-Start relevant).
        self._off_since = None
        self._was_running: bool | None = None
        # Logbuch.
        self._last_logged: int | None = None
        self._setpoint_eid: str | None = None
        # Manueller Eingriff (Display/HA): Sollwert-Schutz bis zum nächsten Morgen-Start.
        self._last_written: int | None = None  # zuletzt SELBST geschriebener Sollwert
        self._manual_hold = False              # manueller Eingriff aktiv -> Sollwert nicht überschreiben
        self._manual_day = None                # Kalendertag, an dem der Override begann (Fallback-Release)
        self._last_kick_day = None             # Datum des letzten Morgen-Starts (1×/Tag)
        self._store: Store | None = None       # Persistenz für _last_kick_day
        self._loaded = False                   # Store schon einmal geladen?
        # Live-Status (vom Diagnose-Sensor gelesen): aktueller Regel-Zustand.
        #   state: off | base | normal | high_boost | high_elec | manual
        #   (interne Keys – die Anzeigetexte lauten Normal/Erhöht/Boost, s. Übersetzungen)
        self.status: dict = {
            "state": "off", "surplus": None, "setpoint": None,
            "running": None, "heater": False,
        }

    def _set_status(self, state, surplus, setpoint, running, heater) -> None:
        self.status = {
            "state": state,
            "surplus": None if surplus is None else round(float(surplus)),
            "setpoint": None if setpoint is None else int(setpoint),
            "running": running,
            "heater": heater,
        }

    async def _ensure_loaded(self, coordinator) -> None:
        """Persistierten Morgen-Start-Tag einmalig aus der Statusdatei laden.

        Überlebt HA-Neustarts: hat der gespeicherte Zeitstempel heutiges Datum,
        gilt der Morgen-Start als „heute schon erledigt" und feuert nicht erneut.
        """
        if self._loaded:
            return
        self._loaded = True
        self._store = Store(
            self.hass, _STORAGE_VERSION, f"{DOMAIN}_pv_{coordinator.entry.entry_id}"
        )
        try:
            data = await self._store.async_load()
        except Exception:  # noqa: BLE001
            data = None
        if data and data.get("last_kick_day"):
            self._last_kick_day = dt_util.parse_date(data["last_kick_day"])

    async def _mark_kicked(self, day) -> None:
        """Morgen-Start-Tag setzen und in die Statusdatei schreiben."""
        self._last_kick_day = day
        if self._store is not None:
            await self._store.async_save({"last_kick_day": day.isoformat()})

    def _reset(self) -> None:
        self._wp_cand = None
        self._wp_since = None
        self._heater_cand = None
        self._heater_since = None
        # Manuellen Sollwert-Schutz beim Verlassen des Coordinator-Modus lösen.
        self._manual_hold = False
        self._manual_day = None
        self._last_written = None

    async def _write_setpoint(self, coordinator, target: int) -> None:
        """Sollwert schreiben und als zuletzt SELBST geschriebenen Wert merken.

        Nur über diesen Pfad geschriebene Werte aktualisieren ``_last_written``;
        User-Wege (Number-/Water-Heater-Entity) laufen über
        ``coordinator.async_write_register`` und fassen ihn nicht an – so lässt
        sich ein fremder (manueller) Eingriff sicher unterscheiden.
        """
        await coordinator.write_value(REG_SET_TEMP, target)
        self._last_written = target

    def _announce(self, coordinator, target: int, surplus: float, up: bool) -> None:
        """Sollwert-Wechsel ins HA-Logbuch (Dedup auf den Zielwert -> wenige Einträge)."""
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

    def _start_allowed(self, o: dict, running: bool, now) -> bool:
        """Anti-Takt für den Morgen-Start: läuft die WP -> ok; sonst nach Mindest-Stillstand."""
        if running:
            return True
        if self._off_since is None:
            return True
        min_off_s = o.get(CONF_PV_MIN_OFF, DEFAULT_PV_MIN_OFF) * 60
        return (now - self._off_since).total_seconds() >= min_off_s

    @staticmethod
    def _debounced(cand_attr, since_attr, want, now, debounce_s, controller, applied):
        """Generischer Entpreller: gibt den neuen angewandten Wert zurück.

        Ändert sich ``want``, startet der Timer neu; erst wenn ``want`` die
        Entprellzeit stabil bleibt, wird er übernommen, sonst bleibt ``applied``.
        """
        if getattr(controller, cand_attr) != want:
            setattr(controller, cand_attr, want)
            setattr(controller, since_attr, now)
            return applied
        since = getattr(controller, since_attr)
        if since is not None and (now - since).total_seconds() >= debounce_s:
            return want
        return applied

    async def async_evaluate(self, coordinator, data: dict[int, int]) -> None:
        o = coordinator.entry.options
        if o.get(CONF_PV_MODE) != PV_MODE_COORDINATOR:
            self._reset()
            self._set_status("off", None, None, None, False)
            return

        # Läuft gerade die Legionellen-Desinfektion, besitzt sie Sollwert/Modus
        # (65 °C). Die PV-Sollwert-Regelung pausiert, damit sie nicht dagegen
        # schreibt (bzw. den 65-°C-Sollwert als manuellen Eingriff fehldeutet).
        if coordinator.legionella.active:
            return

        await self._ensure_loaded(coordinator)

        surplus = state_float(self.hass, o.get(CONF_PV_SENSOR))
        if surplus is None:
            return

        now = dt_util.now()
        running = bool((data.get(REG_STATUS) or 0) & STATUS_HEATPUMP)
        # Stillstand-Zeitstempel pflegen (für Anti-Takt im Morgen-Start).
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
        hold = float(o.get(CONF_PV_HOLD, DEFAULT_PV_HOLD))
        hoch = float(o.get(CONF_PV_HIGH, DEFAULT_PV_HIGH))
        choice = o.get(CONF_PV_ESCALATION, PV_ESC_NONE)
        debounce_s = o.get(CONF_PV_DEBOUNCE, DEFAULT_PV_DEBOUNCE) * 60

        # WP-Zyklus-Ziel aus dem Ist ableiten, falls noch nicht bekannt.
        if self._wp_target is None:
            self._wp_target = t_normal if current >= t_normal - 0.5 else t_base

        # Baseline für die Manuell-Erkennung setzen, falls noch nie selbst
        # geschrieben (frischer Start/Reload). Ohne das bleibt ``_last_written``
        # ``None`` und der allererste manuelle Eingriff (Display/HA) wird nicht
        # erkannt, sondern beim nächsten Poll stillschweigend überschrieben –
        # insbesondere wenn der Sollwert seit dem Start ohnehin schon beim
        # PV-Ziel steht und die PV-Steuerung deshalb nie selbst schreiben musste.
        if self._last_written is None:
            self._last_written = int(current)

        # 1) Morgen-Start (der einzige Kaltstart/Tag): max. 1×/Tag (über die
        #    persistierte ``_last_kick_day`` – überlebt Neustarts) und nur im
        #    Zeitfenster ab der Morgen-Uhrzeit (kein Abend-Kaltstart nach Neustart).
        morning = _parse_time(o.get(CONF_PV_MORNING_TIME, DEFAULT_PV_MORNING_TIME))
        morning_dt = now.replace(hour=morning.hour, minute=morning.minute,
                                 second=0, microsecond=0)
        in_morning_window = morning_dt <= now < morning_dt + timedelta(hours=_MORNING_WINDOW_H)
        if (o.get(CONF_PV_MORNING_ENABLED, DEFAULT_PV_MORNING_ENABLED)
                and in_morning_window and self._last_kick_day != now.date()):
            await self._mark_kicked(now.date())
            # Natürlicher täglicher Reset: ein evtl. manueller Sollwert-Schutz
            # endet mit dem Morgen-Start; die PV-Steuerung übernimmt wieder.
            self._manual_hold = False
            self._manual_day = None
            self._last_written = None
            if water < t_base and current < t_normal and self._start_allowed(o, running, now):
                self._wp_target = t_normal
                target = int(min(max(int(t_normal), SET_TEMP_MIN), SET_TEMP_MAX))
                await self._write_setpoint(coordinator, target)
                _LOGGER.debug("PV: Morgen-Start Soll -> %d (Überschuss %.0f W)", target, surplus)
                self._announce(coordinator, target, surplus, up=True)
                self._set_status("normal", surplus, target, running, False)
                return

        # 2) Schicht 2 – Heizstab (entprellt). Boost nur wenn WP läuft, ELEC nur wenn WP aus.
        if choice == PV_ESC_BOOST:
            heater_want = running and surplus >= hoch
        elif choice == PV_ESC_ELEC:
            heater_want = (not running) and surplus >= hoch
        else:
            heater_want = False
        self._heater_on = self._debounced(
            "_heater_cand", "_heater_since", heater_want, now, debounce_s, self, self._heater_on
        )

        # 3) Schicht 1 – WP-Zyklus-Ziel (Normal/Erhöht, entprellt).
        if self._wp_target <= t_base + 0.5:        # aktuell Normal
            # Anheben nur bei laufender WP (Piggyback, kein Kaltstart).
            wp_want = t_normal if (running and surplus >= hold) else t_base
        else:                                       # aktuell Erhöht
            # Halten solange Überschuss ≥ Halte ODER der Heizstab läuft; sonst absenken.
            wp_want = t_normal if (surplus >= hold or self._heater_on) else t_base
        self._wp_target = self._debounced(
            "_wp_cand", "_wp_since", wp_want, now, debounce_s, self, self._wp_target
        )

        # 4) Effektiver Sollwert: Heizstab hebt auf Boost; sonst der WP-Zyklus-Sollwert.
        #    Manueller Eingriff (Display/HA) = Ist-Sollwert weicht vom zuletzt
        #    SELBST geschriebenen Wert ab -> Sollwert bis zum nächsten Morgen-Start
        #    in Ruhe lassen. Sicherheitsnetz für den Fall „Morgen-Start deaktiviert":
        #    Schutz auch beim Tageswechsel aufheben.
        if (self._manual_hold and self._manual_day is not None
                and now.date() != self._manual_day):
            self._manual_hold = False
            self._manual_day = None
            self._last_written = None
        if self._last_written is not None and int(current) != int(self._last_written):
            if not self._manual_hold:
                self._manual_hold = True
                self._manual_day = now.date()
                _LOGGER.debug("PV: manueller Eingriff erkannt (Soll %d) -> Schutz bis Morgen-Start",
                              int(current))

        effective = t_high if self._heater_on else self._wp_target
        target = int(min(max(int(effective), SET_TEMP_MIN), SET_TEMP_MAX))
        if not self._manual_hold and int(current) != target:
            up = target > int(current)
            await self._write_setpoint(coordinator, target)
            _LOGGER.debug("PV: Soll %d -> %d (%s, Überschuss %.0f W, Heizstab %s)",
                          int(current), target, "hoch" if up else "runter", surplus,
                          "an" if self._heater_on else "aus")
            self._announce(coordinator, target, surplus, up=up)

        # 5) Heizstab-Hardware idempotent setzen/aufräumen.
        await self._apply_heater(coordinator, data, choice, surplus)

        # 6) Live-Status für den Diagnose-Sensor ableiten.
        if self._manual_hold:
            # Manueller Eingriff aktiv: Ist-Sollwert steht, Heizstab-Schicht läuft weiter.
            self._set_status("manual", surplus, int(current), running, self._heater_on)
            return
        if self._heater_on and choice == PV_ESC_BOOST:
            state = "high_boost"
        elif self._heater_on and choice == PV_ESC_ELEC:
            state = "high_elec"
        elif self._wp_target >= t_normal - 0.5:
            state = "normal"
        else:
            state = "base"
        self._set_status(state, surplus, target, running, self._heater_on)

    async def _apply_heater(self, coordinator, data, choice, surplus: float) -> None:
        """Boost-Bit (Reg 2) bzw. Modus ELEC (Reg 1) idempotent nach ``self._heater_on``
        setzen – inkl. Aufräumen, wenn die Eskalations-Option gewechselt hat.
        """
        want_boost = self._heater_on and choice == PV_ESC_BOOST
        want_elec = self._heater_on and choice == PV_ESC_ELEC

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
