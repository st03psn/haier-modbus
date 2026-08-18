"""Optionale PV-Überschuss-Steuerung (Coordinator-Modus) innerhalb der Integration.

Seit v1.16.0 **drei Stufen** (``base`` -> ``Erhöht`` -> ``Boost``, ELEC ist keine
PV-Eskalation mehr, s. u.), geregelt nach PV-Überschuss (``sensor.pv_uberschuss_watt``,
kappt bei 0):

**Schicht 1 — WP-Zyklus, 2-stufig (Normal 50 -> Erhöht 60), auf dem *rohen* Überschuss:**
Das Anheben des Sollwerts erzeugt keine Zusatzlast, daher braucht diese Schicht keine
Normalisierung.
- **Fixer Morgen-Start (1×/Tag):** zur Uhrzeit, wenn Wasser unter Basis liegt, Sollwert
  auf **Basis** in **ECO** -> die WP macht eine effiziente Grundladung. Bewusst *nicht*
  Erhöht/AUTO: der Morgen-Start ist der garantierte Tagesstart, keine Überschuss-Reaktion
  (sonst käme an trüben Tagen die volle Ladung aus dem Netz). Die Anhebung auf Erhöht +
  AUTO folgt bei Überschuss über den Piggyback-Zweig – ohne neues Startkontingent.
- **Tages-Kaltstart:** überschussgetrieben, mit **Mindestdefizit** – Wasser ≤
  ``Erhöht-Ziel − pv_coldstart_delta`` (Default 10 K), voll entprellter Überschuss ≥
  ``pv_coldstart``, Anti-Takt erfüllt UND das Tageskontingent (``pv_max_starts``,
  Default 3) noch nicht ausgeschöpft. Das Defizit verhindert Starts für wenige Grad im
  schlechtesten Teil der Kennlinie; das Kontingent ist nur noch Notbremse, denn die
  eigentliche Taktbremse ist ``pv_min_off``.
- **Anheben Normal->Erhöht nur bei LAUFENDER WP** (Piggyback) + Überschuss ≥ Halte-Puffer.
- **Mindestlaufzeit** (``pv_min_run``, Default 30 min): ein einmal gestarteter Zyklus wird
  garantiert so lange gehalten, unabhängig vom Überschuss – eine durchziehende Wolke darf
  ihn nicht abwürgen. Symmetrisch zu ``pv_min_off`` (Mindest-Stillstand vor dem nächsten
  Start).
- **Rückfall auf Basis + ECO, sobald ein Zyklus endet** (AP6b) – auch mitten am Tag, damit
  der Tagesplan hält. Ein erneutes Anheben muss Anti-Takt und Tageskontingent erneut
  passieren.
- **Nachts gilt schlicht die Basis-Zieltemperatur in ECO** – es gibt bewusst *keine*
  zusätzliche Nachtabsenkung. Der Rückfall auf Basis+ECO (oben) ist bereits das
  Nachtverhalten; ein noch tieferer Boden brächte PV-seitig nichts (den Fall „Speicher
  morgens voll bei 50 °C, Sonne kommt" deckt der Tages-Kaltstart ab) und nähme nur die
  Reserve für ungewöhnlich hohen Warmwasserbedarf. Fällt die Temperatur nachts unter die
  Basis, heizt das Gerät regulär nach; wird es kritisch, eskaliert ``emergency.py``.

**Schicht 2 — Heizstab/Boost, auf dem *normalisierten* Überschuss ("verfügbar"):**
- Der Überschusssensor ist einspeisungsbasiert (Eigenaufnahme bereits abgezogen) – der
  Heizstab senkt beim Einschalten seinen eigenen Messwert. ``verfügbar`` macht das Signal
  invariant gegen die eigene Schalthandlung:
  ``verfügbar = roher_Überschuss + (Heizstab an ? P_heizstab : 0)``. ``P_heizstab`` ist der
  Nennwert (Datenblatt, 1500 W) oder – optional – der real gemessene Einschalt-Zuwachs.
- **Boost** (WP+Heizstab, Reg 2 bit1): heißt, was der Name sagt – beide **gemeinsam**, nur
  bei bereits laufender WP. Boost ist eine **Leistungssenke, keine eigene Temperaturstufe**
  – die Zieltemperatur bleibt die der Erhöht-Stufe (``pv_temp_normal``).
- **Ein/Aus – eine einzige Schwelle** ``pv_high`` auf ``verfügbar``: **Ein** entprellt
  (volle Zeit, schützt gegen Sensor-Ausreißer), **Aus sofort** (ein Poll) – asymmetrisch,
  weil Bezug beim Heizstab strikt vermieden werden soll. ``pv_high`` wird gegen die
  Heizstab-Leistung geklemmt (``pv_high >= P_heizstab + 50``), sonst schaltete der
  Heizstab in den Netzbezug hinein ab.
- Optional an einen Negativpreis-Sensor koppelbar (Gate, kein Schwellensenker): ist
  ``pv_boost_only_negative_price`` gesetzt, feuert Boost nur, wenn der Sensor aktiv ist.
- Fällt der Überschuss unter die Schwelle: nur der Heizstab geht weg; die WP läuft
  unverändert weiter (Schicht 1 unberührt).

**Modus (AP4):** ``base`` -> ECO, ``Erhöht``/``Boost`` -> AUTO, idempotent. Harte
Invariante: AUTO nur, wenn der geschriebene Sollwert ≤ ``WP_MAX_TEMP`` ist – oberhalb
zieht das Gerät laut Datenblatt selbsttätig den Heizstab (unbelegter Teil der
Nutzerannahme). Mit Boost == Erhöht-Ziel ist das konstruktiv erfüllt. Rangfolge: Die
Leiter tritt bei Modus-Schreibzugriffen zurück, wenn Legionellen-Schutz oder Notheizung
aktiv sind – beide besitzen dann den Modus.

**ELEC** ist seit v1.16.0 **keine PV-Eskalation mehr** – reine Notfall-Option in
``emergency.py`` (``CONF_EMERGENCY_MODE``), weil Reg 1 ein *Wert* ist (kein Bitfeld) und
"ELEC als Bit schalten" nicht existiert.

Nur im **Coordinator**-Modus aktiv; in **Aus**/**Executor** steigt ``async_evaluate``
sofort aus. Schreibzugriffe sind idempotent (nur bei Abweichung).

**Config-Änderungen mitten im Lauf:** Jede Options-Änderung außerhalb ``LIVE_OPTION_KEYS``
lädt die Integration komplett neu (auch dieser Controller wird neu instanziiert). Läuft die
WP dabei gerade, wird der vorgefundene Sollwert für den Rest dieses Zyklus **gehalten** –
eine z. B. reduzierte Normaltemperatur senkt einen bereits laufenden Erhöht-Zyklus nicht
mitten drin ab. Erst wenn die WP wieder aus ist, greift die (ggf. neue) Config normal ab
dem nächsten Zyklus.
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
    CONF_PV_BOOST_ONLY_NEGATIVE_PRICE,
    CONF_PV_COLDSTART,
    CONF_PV_COLDSTART_DELTA,
    CONF_PV_DEBOUNCE,
    CONF_PV_ESCALATION,
    CONF_PV_HEATER_POWER,
    CONF_PV_HIGH,
    CONF_PV_HOLD,
    CONF_PV_MAX_STARTS,
    CONF_PV_MIN_OFF,
    CONF_PV_MIN_RUN,
    CONF_PV_MODE,
    CONF_PV_MORNING_ENABLED,
    CONF_PV_MORNING_TIME,
    CONF_PV_NEGATIVE_PRICE_SENSOR,
    CONF_PV_POWER_ENTITY,
    CONF_PV_SENSOR,
    CONF_PV_TEMP_BASE,
    CONF_PV_TEMP_NORMAL,
    DEFAULT_PV_COLDSTART,
    DEFAULT_PV_COLDSTART_DELTA,
    DEFAULT_PV_DEBOUNCE,
    DEFAULT_PV_HEATER_POWER,
    DEFAULT_PV_HIGH,
    DEFAULT_PV_HOLD,
    DEFAULT_PV_MAX_STARTS,
    DEFAULT_PV_MIN_OFF,
    DEFAULT_PV_MIN_RUN,
    DEFAULT_PV_MORNING_ENABLED,
    DEFAULT_PV_MORNING_TIME,
    DEFAULT_PV_TEMP_BASE,
    DEFAULT_PV_TEMP_NORMAL,
    DOMAIN,
    MODE_AUTO,
    MODE_ECO,
    PV_ESC_BOOST,
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
    WP_MAX_TEMP,
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
    """Coordinator-Modus: WP-Zyklus (Schicht 1) + Heizstab/Boost (Schicht 2)."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        # Schicht 1 (WP-Zyklus): entprellter Ziel-Zustand (Basis/Erhöht).
        self._wp_target: float | None = None   # aktueller WP-Zyklus-Sollwert (Basis/Erhöht)
        self._wp_cand: float | None = None      # entprellter Kandidat
        self._wp_since = None
        # Schicht 2 (Heizstab/Boost): asymmetrisch entprellter An/Aus-Zustand
        # (Ein = volle Entprellzeit, Aus = sofort, s. Modul-Docstring AP3).
        self._heater_on = False
        self._heater_cand: bool | None = None
        self._heater_since = None
        self._boost_applied = False            # Boost-Bit von uns gesetzt?
        # Geräte-Gesamtleistung unmittelbar vor dem letzten Heizstab-Einschalten
        # (optionale Verfeinerung der Heizstab-Leistungsschätzung, AP3).
        self._power_baseline: float | None = None
        # Tages-Kaltstart (AP6a): eigener Entpreller (Wasser < Erhöht + Überschuss).
        self._coldstart_cand: bool | None = None
        self._coldstart_since = None
        self._coldstart_ready = False
        # Anti-Takt (jetzt für jede Anhebung bei stehender WP relevant, nicht mehr
        # nur für den Morgen-Start).
        self._off_since = None
        self._was_running: bool | None = None
        # Mindestlaufzeit (v1.16.4): Zeitpunkt, seit dem die WP UNUNTERBROCHEN läuft.
        self._run_since = None
        # Lief die WP schon beim (Neu-)Start/Reload dieses Controllers, wird der
        # dann vorgefundene Sollwert für den Rest dieses Laufs gehalten – eine
        # zeitgleiche Config-Änderung (z. B. reduzierte Normaltemperatur) darf
        # einen bereits laufenden Zyklus nicht mitten drin absenken/anheben.
        # Löst sich, sobald die WP wieder aus ist; danach gilt die (ggf. neue)
        # Config normal ab dem nächsten Zyklus.
        self._hold_run = False
        # Logbuch.
        self._last_logged: int | None = None
        self._setpoint_eid: str | None = None
        # Manueller Eingriff (Display/HA): Sollwert-Schutz bis zum nächsten Morgen-Start.
        self._last_written: int | None = None  # zuletzt SELBST geschriebener Sollwert
        self._manual_hold = False              # manueller Eingriff aktiv -> Sollwert nicht überschreiben
        self._manual_day = None                # Kalendertag, an dem der Override begann (Fallback-Release)
        self._last_kick_day = None             # Datum des letzten Morgen-Starts (1×/Tag)
        self._starts_day = None                # Datum, für das _starts_count zählt (AP6a)
        self._starts_count = 0                 # von der Leiter ausgelöste Starts an _starts_day
        self._store: Store | None = None       # Persistenz für _last_kick_day/_starts_*
        self._loaded = False                   # Store schon einmal geladen?
        self._pv_high_clamped_warned = False   # einmalige Warnung bei verdrehtem pv_high
        # Live-Status (vom Diagnose-Sensor gelesen): aktueller Regel-Zustand.
        #   state: off | base | normal | boost | manual | held
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
        """Persistierten Tagesplan-Stand einmalig aus der Statusdatei laden.

        Überlebt HA-Neustarts UND Reloads: sowohl der Morgen-Start-Tag als auch der
        Tages-Startzähler (AP6a) hängen an dieser Datei, nicht am In-Memory-Zustand des
        Controllers – ein Reload (z. B. durch eine nicht-live Options-Änderung) darf das
        Tageskontingent nicht zurücksetzen.
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
        if data:
            if data.get("last_kick_day"):
                self._last_kick_day = dt_util.parse_date(data["last_kick_day"])
            if data.get("starts_day"):
                self._starts_day = dt_util.parse_date(data["starts_day"])
            self._starts_count = int(data.get("starts_count") or 0)

    async def _save_store(self) -> None:
        if self._store is None:
            return
        await self._store.async_save({
            "last_kick_day": self._last_kick_day.isoformat() if self._last_kick_day else None,
            "starts_day": self._starts_day.isoformat() if self._starts_day else None,
            "starts_count": self._starts_count,
        })

    async def _mark_kicked(self, day) -> None:
        """Morgen-Start-Tag setzen und in die Statusdatei schreiben."""
        self._last_kick_day = day
        await self._save_store()

    def _starts_today(self, day) -> int:
        """Anzahl der von der Leiter ausgelösten Starts am gegebenen Tag (AP6a)."""
        return self._starts_count if self._starts_day == day else 0

    async def _register_start(self, day) -> None:
        """Einen von der Leiter ausgelösten Start zählen (Morgen-Start ODER Kaltstart
        teilen sich dieses Kontingent – zusammen i. d. R. ein Lauf/Tag)."""
        if self._starts_day != day:
            self._starts_day = day
            self._starts_count = 0
        self._starts_count += 1
        await self._save_store()

    def _reset(self) -> None:
        self._wp_cand = None
        self._wp_since = None
        self._heater_cand = None
        self._heater_since = None
        self._coldstart_cand = None
        self._coldstart_since = None
        self._coldstart_ready = False
        self._hold_run = False
        self._run_since = None
        # Manuellen Sollwert-Schutz beim Verlassen des Coordinator-Modus lösen.
        self._manual_hold = False
        self._manual_day = None
        self._last_written = None

    async def _write_setpoint(self, coordinator, target: int) -> bool:
        """Sollwert schreiben und als zuletzt SELBST geschriebenen Wert merken.

        Nur über diesen Pfad geschriebene Werte aktualisieren ``_last_written``;
        User-Wege (Number-/Water-Heater-Entity) laufen über
        ``coordinator.async_write_register`` und fassen ihn nicht an – so lässt
        sich ein fremder (manueller) Eingriff sicher unterscheiden.

        ``_last_written`` wird **nur bei erfolgreichem Schreiben** fortgeschrieben:
        Bei einem abgelehnten Zugriff bliebe sonst der alte Registerwert stehen,
        während ``_last_written`` schon den neuen Zielwert trüge – die nächste
        Auswertung hielte die Abweichung für einen manuellen Eingriff und die
        Leiter würde sich für den Rest des Tages zurückziehen.
        """
        ok = await coordinator.write_value(REG_SET_TEMP, target)
        if ok:
            self._last_written = target
        return ok

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

    def _temps(self, o: dict) -> tuple[float, float]:
        """(Erhöht-Zieltemp, Basis-Zieltemp), Gerätegrenze erzwungen.

        Erhöht ist seit AP2 zugleich die Boost-Zieltemperatur (Boost ist eine
        Leistungssenke, keine eigene Temperaturstufe) und muss daher unabhängig von
        ``pv_temp_high`` (nur noch für den Executor relevant) auf ``WP_MAX_TEMP``
        begrenzt werden – das ist die harte Invariante aus AP4.
        """
        t_normal = float(o.get(CONF_PV_TEMP_NORMAL, DEFAULT_PV_TEMP_NORMAL))
        t_base = float(o.get(CONF_PV_TEMP_BASE, DEFAULT_PV_TEMP_BASE))
        t_normal = min(max(t_normal, t_base), float(WP_MAX_TEMP))
        return t_normal, t_base

    def _clamp_pv_high(self, hoch: float, p_heater_nominal: float) -> float:
        """``pv_high`` gegen die Heizstab-Nennleistung klemmen (AP3, Sicherheitsventil).

        Verletzt die Konfiguration ``pv_high >= P_heizstab + 50``, schaltet der Heizstab
        in den Netzbezug hinein ab (die Reserve wird negativ). Hochklemmen + einmalig
        warnen statt stillschweigend takten lassen.
        """
        min_hoch = p_heater_nominal + 50
        if hoch >= min_hoch:
            return hoch
        if not self._pv_high_clamped_warned:
            _LOGGER.warning(
                "PV: pv_high (%.0f W) liegt unter Heizstableistung + 50 W (%.0f W) -> "
                "auf %.0f W hochgeklemmt, sonst schaltet der Heizstab in den Netzbezug "
                "hinein ab",
                hoch, min_hoch, min_hoch,
            )
            self._pv_high_clamped_warned = True
        return min_hoch

    def _heater_power_watts(self, o: dict, nominal: float) -> float:
        """Geschätzte Heizstab-Leistung für die Verfügbar-Normalisierung (AP3).

        Ohne konfigurierte Leistungs-Entität: der Nennwert (Datenblatt, ohmsche Last,
        exakt – ein Messsensor ist nicht erforderlich). Mit Entität: der real gemessene
        Einschalt-Zuwachs (Ist-Leistung minus Baseline unmittelbar vor dem Einschalten),
        plausibilitätsgeklemmt auf [0,7·Nennwert, 1,3·Nennwert]; außerhalb -> Rückfall auf
        den Nennwert (z. B. beim allerersten Einschalten, wenn noch keine Baseline vorliegt).
        """
        entity = o.get(CONF_PV_POWER_ENTITY)
        if not entity:
            return nominal
        power_now = state_float(self.hass, entity)
        if not self._heater_on:
            # Heizstab aus: Baseline für die nächste Einschaltung nachführen.
            if power_now is not None:
                self._power_baseline = power_now
            return nominal
        if power_now is None or self._power_baseline is None:
            return nominal
        measured = power_now - self._power_baseline
        if 0.7 * nominal <= measured <= 1.3 * nominal:
            return measured
        return nominal

    def _negative_price(self, o: dict) -> bool:
        """True, wenn ein optionaler Negativpreis-Sensor konfiguriert und aktiv ist.

        Kein Sensor konfiguriert -> immer False (sicherer Fallback: kein fälschliches
        Zuschalten). Erwartet einen ``binary_sensor``/``input_boolean``, der die aktuelle
        Viertelstunde als Negativ-/Null-Preis markiert (z. B. eigenes Template über
        Tibber/aWATTar/Nordpool – die Integration berechnet den Preis nicht selbst).
        """
        entity_id = o.get(CONF_PV_NEGATIVE_PRICE_SENSOR)
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == "on"

    def _start_allowed(self, o: dict, running: bool, now) -> bool:
        """Anti-Takt für JEDE Sollwert-Anhebung bei stehender WP (Morgen-Start UND
        Tages-Kaltstart, AP6a): läuft die WP -> ok; sonst nach Mindest-Stillstand."""
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

    async def _apply_mode(self, coordinator, data, want_mode: int, target: int) -> None:
        """ECO/AUTO nach WP-Zyklus-Stufe setzen (AP4), idempotent.

        Rangfolge: Die Notheizung hat Vorrang für den Modus – hier zurücktreten, wenn sie
        gerade forciert (analog zum Legionellen-Guard in ``async_evaluate``, aber nur für
        den Modus – die Notheizung besitzt kein Sollwert-Feld).
        Nur die eigene Domäne (ECO/AUTO) wird angefasst; ein fremd gesetzter Modus (ELEC =
        Notheizung im Modus "elec", VAC = Nutzer) bleibt unberührt.
        Harte Invariante: AUTO nur, wenn der Sollwert ≤ ``WP_MAX_TEMP`` ist – oberhalb
        zieht das Gerät laut Datenblatt selbsttätig den Heizstab (unbelegter Teil der
        Nutzerannahme, s. Plan). Mit Boost == Erhöht-Ziel (AP2) ist das konstruktiv
        erfüllt; die Assertion sichert das gegen künftige Änderungen ab.
        """
        if coordinator.emergency.active:
            return
        mode = data.get(REG_MODE)
        if mode is None or mode not in (MODE_ECO, MODE_AUTO):
            return
        if want_mode == MODE_AUTO:
            assert target <= WP_MAX_TEMP, "PV: AUTO nur mit Sollwert <= WP_MAX_TEMP (Invariante AP4)"
        if mode != want_mode and await coordinator.write_value(REG_MODE, want_mode):
            _LOGGER.debug("PV: Modus -> %s", "AUTO" if want_mode == MODE_AUTO else "ECO")

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

        current = data.get(REG_SET_TEMP)
        if current is None:
            return
        current = float(current)
        water = float(data.get(REG_WATER_TEMP) or 0)

        t_normal, t_base = self._temps(o)
        hold = float(o.get(CONF_PV_HOLD, DEFAULT_PV_HOLD))
        p_heater_nominal = float(o.get(CONF_PV_HEATER_POWER, DEFAULT_PV_HEATER_POWER))
        hoch = self._clamp_pv_high(float(o.get(CONF_PV_HIGH, DEFAULT_PV_HIGH)), p_heater_nominal)
        choice = o.get(CONF_PV_ESCALATION, PV_ESC_NONE)
        debounce_s = o.get(CONF_PV_DEBOUNCE, DEFAULT_PV_DEBOUNCE) * 60

        # Normalisierung (AP3): "verfügbar" ist invariant gegen die eigene
        # Heizstab-Schalthandlung – Grundlage für Schicht 2 (nicht für Schicht 1, das
        # Anheben des Sollwerts erzeugt keine Zusatzlast).
        p_heater = self._heater_power_watts(o, p_heater_nominal)
        available = surplus + (p_heater if self._heater_on else 0.0)

        # Stillstand-Zeitstempel pflegen (Anti-Takt) + Tagesplan-Rückfall (AP6b) +
        # Laufzeit-Zeitstempel für die Mindestlaufzeit (v1.16.4, s. u.).
        if running:
            self._off_since = None
            if not self._was_running:
                self._run_since = now          # steigende Flanke: Zyklus beginnt
        elif self._was_running:
            self._off_since = now
            self._run_since = None
            self._hold_run = False
            # Zyklus abgeschlossen -> Sollwert/Modus zurück auf Basis, auch mitten am
            # Tag (AP6b). Damit gilt nachts die Basis-Zieltemperatur in ECO – bewusst
            # ohne zusätzliche Absenkung, s. Modul-Docstring.
            self._wp_target = t_base
            self._wp_cand = None
            self._wp_since = None
        self._was_running = running

        # WP-Zyklus-Ziel aus dem Ist ableiten, falls noch nicht bekannt (frischer
        # Start/Reload). Bewusst der *unveränderte* Register-Sollwert, nicht anhand der
        # (ggf. gerade geänderten) Zieltemperaturen neu einsortiert – sonst würde z. B.
        # eine reduzierte Normaltemperatur einen laufenden Erhöht-Zyklus beim Reload
        # sofort neu bewerten und absenken.
        if self._wp_target is None:
            self._wp_target = current
            if running:
                self._hold_run = True

        # Baseline für die Manuell-Erkennung setzen, falls noch nie selbst geschrieben.
        if self._last_written is None:
            self._last_written = int(current)

        max_starts = int(o.get(CONF_PV_MAX_STARTS, DEFAULT_PV_MAX_STARTS))

        # 1) Fixer Morgen-Start (der klassische Kaltstart): max. 1×/Tag (über die
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
            # Der Morgen-Start ist der GARANTIERTE Tagesstart, keine Überschuss-Reaktion:
            # deshalb Basis-Zieltemperatur in ECO (nicht Erhöht/AUTO). Sonst lüde er an
            # trüben Tagen den vollen Speicher aus dem Netz. Die Anhebung auf Erhöht +
            # AUTO passiert danach von selbst über den Piggyback-Zweig in Schicht 1 –
            # OHNE erneutes ``_register_start()`` (die WP läuft dann bereits).
            #
            # WICHTIG – ``int(current) != target``: Seit die Nachtabsenkung entfallen
            # ist, steht der Sollwert nachts ohnehin schon auf der Basis. Ohne diese
            # Prüfung schriebe der Morgen-Start 50 auf 50 (wirkungslos), verbrauchte
            # dabei aber das Tageskontingent – und der überschussgetriebene Kaltstart
            # käme den ganzen Tag nicht mehr zum Zug. Ein Start wird deshalb nur
            # gezählt, wenn der Sollwert tatsächlich angehoben wird.
            target = int(min(max(int(t_base), SET_TEMP_MIN), SET_TEMP_MAX))
            if (water < t_base and current < t_normal and int(current) != target
                    and self._starts_today(now.date()) < max_starts
                    and self._start_allowed(o, running, now)):
                self._wp_target = t_base
                await self._write_setpoint(coordinator, target)
                await self._register_start(now.date())
                await self._apply_mode(coordinator, data, MODE_ECO, target)
                _LOGGER.debug("PV: Morgen-Start Soll -> %d (ECO, Überschuss %.0f W)", target, surplus)
                self._announce(coordinator, target, surplus, up=True)
                self._set_status("base", surplus, target, running, False)
                return

        # 2) Tages-Kaltstart (AP6a): überschussgetrieben, mit MINDESTDEFIZIT.
        #    Nutzt denselben Anti-Takt-Guard wie der Morgen-Start (``_start_allowed``
        #    gilt für jede Anhebung bei stehender WP).
        #
        #    Warum ein Mindestdefizit (v1.16.3): Die frühere Bedingung ``water < t_normal``
        #    war fast immer wahr, weil ``t_normal`` typischerweise auf der Verdichtergrenze
        #    (65 °C) steht und der Speicher nie exakt dort liegt – er verliert ständig
        #    Wärme. Real belegt am 12.08.: Bei Wasser 61 °C und Ziel 65 °C wurde der
        #    Verdichter für **4 K** angeworfen. Das ist die schlechteste Wärme des Tages:
        #    oberhalb 60 °C fällt die Aufheizrate laut Feldmessung von 6,0 auf 3,9 K/h
        #    (schlechtester COP), die obersten Grad haben den höchsten Stillstandsverlust,
        #    und die Anlaufverluste verteilen sich auf sehr wenig gewonnene Wärme.
        #    Der Kaltstart soll einen *spürbar entleerten* Speicher laden, nicht die
        #    letzten Grad nachpolieren.
        coldstart_w = float(o.get(CONF_PV_COLDSTART, DEFAULT_PV_COLDSTART))
        coldstart_delta = float(o.get(CONF_PV_COLDSTART_DELTA, DEFAULT_PV_COLDSTART_DELTA))
        coldstart_eligible = (
            not running and water <= t_normal - coldstart_delta
            and self._starts_today(now.date()) < max_starts
        )
        coldstart_want = (
            coldstart_eligible and available >= coldstart_w
            and self._start_allowed(o, running, now)
        )
        if coldstart_want:
            self._coldstart_ready = self._debounced(
                "_coldstart_cand", "_coldstart_since", True, now, debounce_s,
                self, self._coldstart_ready,
            )
        else:
            self._coldstart_cand = None
            self._coldstart_since = None
            self._coldstart_ready = False
        if self._coldstart_ready:
            self._coldstart_ready = False
            self._coldstart_cand = None
            self._coldstart_since = None
            self._manual_hold = False
            self._manual_day = None
            self._last_written = None
            self._wp_target = t_normal
            target = int(min(max(int(t_normal), SET_TEMP_MIN), SET_TEMP_MAX))
            await self._write_setpoint(coordinator, target)
            await self._register_start(now.date())
            await self._apply_mode(coordinator, data, MODE_AUTO, target)
            _LOGGER.debug("PV: Kaltstart Soll -> %d (Überschuss %.0f W)", target, surplus)
            self._announce(coordinator, target, surplus, up=True)
            self._set_status("normal", surplus, target, running, False)
            return

        # 3) Schicht 1 – WP-Zyklus-Ziel (Basis/Erhöht, entprellt, roher Überschuss). Der
        #    Zwischenwert-Zweig wird bewusst EXPLIZIT geprüft (nicht als `else`): seit
        #    v1.13.2 wird ``_wp_target`` aus dem *rohen* Register gebootstrappt (35..75,
        #    nicht zwingend eine Stufe). Ein bares `else` würde einen Bootstrap-Wert
        #    ungeprüft wie die höchste Stufe behandeln.
        if self._wp_target >= t_normal - 0.5:       # aktuell Erhöht
            wp_want = t_normal if (surplus >= hold or self._heater_on) else t_base
        elif self._wp_target <= t_base + 0.5:       # aktuell Basis: nur Piggyback anheben
            wp_want = t_normal if (running and surplus >= hold) else t_base
        else:                                        # Bootstrap-Zwischenwert (kein Kaltstart!)
            wp_want = t_normal if (running and surplus >= hold) else t_base

        # Mindestlaufzeit (v1.16.4, ersetzt die Abbruch-Entprellung aus 1.16.3). Real
        # belegt am 13.08.: Kaltstart 10:53, WP läuft 10:56, um 11:00 bricht der
        # Überschuss von 10 kW auf null ein (Wolke), nach 5 min Entprellung fällt der
        # Sollwert auf Basis unter die Wassertemperatur -> Zyklus nach 10 Minuten
        # abgewürgt. Ab 11:05 lag der Überschuss wieder bei 2700 W im Mittel – die
        # beste Stunde des Tages blieb ungenutzt.
        #
        # Läuft der Verdichter, ist sein Start bereits bezahlt; ihn wegen einer
        # durchziehenden Wolke abzubrechen verschenkt genau diese Investition und
        # kostet sie beim Neustart erneut. Ein einmal gestarteter Zyklus wird deshalb
        # für eine garantierte Mindestdauer (``pv_min_run``, Default 30 min) gehalten –
        # unabhängig davon, wie kurz der Überschuss-Einbruch war. Danach gilt wieder
        # die normale Entprellzeit (``pv_debounce``). Symmetrisch zu ``pv_min_off``
        # (Mindest-Stillstand vor dem nächsten Start): zusammen zwei einfache, klar
        # benannte Zeiten statt einer verlängerten Entprellung.
        min_run_s = o.get(CONF_PV_MIN_RUN, DEFAULT_PV_MIN_RUN) * 60
        run_elapsed_s = (now - self._run_since).total_seconds() if self._run_since else None
        holding_min_run = (
            running
            and self._wp_target >= t_normal - 0.5   # nur relevant, wenn gerade Erhöht läuft
            and run_elapsed_s is not None
            and run_elapsed_s < min_run_s
        )
        if holding_min_run:
            wp_want = t_normal   # Mindestlaufzeit erzwingt Halten, unabhängig vom Überschuss
        self._wp_target = self._debounced(
            "_wp_cand", "_wp_since", wp_want, now, debounce_s, self, self._wp_target
        )

        # 4) Schicht 2 – Heizstab/Boost, asymmetrisch entprellt (Ein = volle Zeit, Aus =
        #    sofort, s. Modul-Docstring) auf dem normalisierten "verfügbar".
        only_negative = bool(o.get(CONF_PV_BOOST_ONLY_NEGATIVE_PRICE, False))
        price_gate_ok = (not only_negative) or self._negative_price(o)
        if choice == PV_ESC_BOOST:
            heater_want = running and available >= hoch and price_gate_ok
        else:
            heater_want = False
        if heater_want:
            self._heater_on = self._debounced(
                "_heater_cand", "_heater_since", True, now, debounce_s, self, self._heater_on
            )
        else:
            self._heater_cand = None
            self._heater_since = None
            self._heater_on = False

        # 5) Effektiver Sollwert: Boost nutzt DENSELBEN Sollwert wie Erhöht (Leistungssenke,
        #    keine eigene Temperaturstufe, AP2) – der WP-Zyklus-Sollwert ist bereits das
        #    Ziel. Manueller Eingriff (Display/HA) = Ist-Sollwert weicht vom zuletzt SELBST
        #    geschriebenen Wert ab -> Sollwert bis zum nächsten Morgen-Start/Kaltstart in
        #    Ruhe lassen.
        if (self._manual_hold and self._manual_day is not None
                and now.date() != self._manual_day):
            self._manual_hold = False
            self._manual_day = None
            self._last_written = None
        if self._last_written is not None and int(current) != int(self._last_written):
            if not self._manual_hold:
                self._manual_hold = True
                self._manual_day = now.date()
                _LOGGER.debug("PV: manueller Eingriff erkannt (Soll %d) -> Schutz bis Morgen-Start/Kaltstart",
                              int(current))

        effective = self._wp_target
        target = int(min(max(int(effective), SET_TEMP_MIN), SET_TEMP_MAX))

        # Halte-Sperre (siehe Bootstrap oben): ein beim Reload bereits laufender
        # Zyklus wird nicht mitten drin umgeschrieben – die (ggf. neue) Config
        # greift erst normal, sobald die WP wieder aus ist.
        if not self._manual_hold and not self._hold_run and int(current) != target:
            up = target > int(current)
            await self._write_setpoint(coordinator, target)
            _LOGGER.debug("PV: Soll %d -> %d (%s, Überschuss %.0f W, Heizstab %s)",
                          int(current), target, "hoch" if up else "runter", surplus,
                          "an" if self._heater_on else "aus")
            self._announce(coordinator, target, surplus, up=up)

        # 6) Heizstab-Hardware (Boost-Bit) idempotent setzen/aufräumen.
        await self._apply_heater(coordinator, data, surplus)

        # 7) Modus ECO/AUTO nach WP-Zyklus-Stufe (AP4) – s. _apply_mode für Rangfolge
        #    und die harte Invariante.
        #    WICHTIG: dieselben Sperren wie beim Sollwert oben. Ein manueller Eingriff
        #    umfasst in der Praxis Sollwert UND Modus (am Display/in HA in einem Zug
        #    gesetzt); würde die Leiter hier weiterschreiben, zöge sie ein von Hand
        #    gesetztes AUTO wieder auf ECO zurück, während sie den Sollwert brav in Ruhe
        #    lässt – der Schutz wäre nur halb wirksam. Ebenso beim gehaltenen Zyklus
        #    (``_hold_run``): ein laufender Zyklus wird nicht mitten drin umgestellt.
        #    Der Heizstab (Schritt 6) bleibt bewusst aktiv – er ist überschussgeführt und
        #    hängt nicht am manuell gesetzten Sollwert.
        if not self._manual_hold and not self._hold_run:
            if self._wp_target >= t_normal - 0.5:   # Erhöht (bzw. Boost, gleiche Zieltemp)
                want_mode = MODE_AUTO
            elif self._wp_target <= t_base + 0.5:   # Basis
                want_mode = MODE_ECO
            else:                                    # Bootstrap-Zwischenwert: konservativ ECO
                want_mode = MODE_ECO
            await self._apply_mode(coordinator, data, want_mode, target)

        # 8) Live-Status für den Diagnose-Sensor ableiten.
        if self._manual_hold:
            # Manueller Eingriff aktiv: Ist-Sollwert steht, Heizstab-Schicht läuft weiter.
            self._set_status("manual", surplus, int(current), running, self._heater_on)
            return
        if self._hold_run:
            # Ein beim Reload bereits laufender Zyklus wird zu Ende gefahren,
            # bevor eine (ggf. neue) Config den Sollwert wieder anfassen darf.
            self._set_status("held", surplus, int(current), running, self._heater_on)
            return
        if self._heater_on:
            state = "boost"
        elif self._wp_target >= t_normal - 0.5:
            state = "normal"
        else:
            state = "base"
        self._set_status(state, surplus, target, running, self._heater_on)

    async def _apply_heater(self, coordinator, data, surplus: float) -> None:
        """Boost-Bit (Reg 2, bit1) idempotent nach ``self._heater_on`` setzen.

        Boost fährt laut Datenblatt WP **und** Heizstab gemeinsam. ELEC (nur Heizstab,
        WP aus) ist seit v1.16.0 keine PV-Eskalation mehr, sondern eine Notfall-Option in
        ``emergency.py`` – der Modus-Besitz für ELEC liegt dort allein.
        """
        func = data.get(REG_FUNCTION)
        if func is None:
            return
        on = bool(func & BIT_BOOST)
        # Besitz-Merker nur bei erfolgreichem Schreiben umschalten: Bliebe er nach einem
        # abgelehnten Zugriff falsch stehen, würde die Leiter entweder ein Bit löschen,
        # das sie nie gesetzt hat, oder – schlimmer – vergessen, dass sie den Heizstab
        # eingeschaltet hat, und ihn nie wieder ausschalten. Ein Fehlversuch wird beim
        # nächsten Poll ohnehin wiederholt, weil sich weder ``on`` noch ``_heater_on``
        # geändert haben.
        if self._heater_on and not on:
            if await coordinator.write_value(REG_FUNCTION, func | BIT_BOOST):
                self._boost_applied = True
                _LOGGER.debug("PV: Boost an (Überschuss %.0f W)", surplus)
        elif not self._heater_on and on and self._boost_applied:
            if await coordinator.write_value(REG_FUNCTION, func & ~BIT_BOOST):
                self._boost_applied = False
                _LOGGER.debug("PV: Boost aus")
