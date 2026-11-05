"""Config- und Options-Flow – alles über die HA-Oberfläche konfigurierbar.

Einrichtungsassistent in drei Schritten:
  1. user  – Verbindungsart wählen, dann ``tcp`` (Konverter) oder ``serial``
             (USB/RS-485-Adapter, #16) – jeweils mit Verbindungstest + Modell
  2. cop   – COP-/Energiequellen
  3. pv    – optionale PV-Überschuss-Steuerung (Sensor + Schwellen)

Der Options-Flow ("Konfigurieren") macht später alles davon änderbar –
inklusive Host/Port/Slave des Modbus-Konverters.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (
    BATTERY_SIGN_CHARGE_NEGATIVE,
    BATTERY_SIGN_CHARGE_POSITIVE,
    CONF_AMBIENT_OFFSET,
    CONF_BAUDRATE,
    CONF_CONNECTION_TYPE,
    CONF_COP_ELEC_ENTITY,
    CONF_COP_ENABLED,
    CONF_COP_HEAT_ENTITY,
    CONF_COP_REF_DATE,
    CONF_DASHBOARD_ENABLED,
    CONF_DASHBOARD_IMAGE,
    CONF_HEAT_EXCHANGER,
    CONF_EMERGENCY_CRITICAL,
    CONF_EMERGENCY_ENABLED,
    CONF_EMERGENCY_MODE,
    CONF_EMERGENCY_RECOVER,
    CONF_ENERGY_SCALE,
    CONF_HOST,
    CONF_LEGIONELLA_BOTTOM,
    CONF_LEGIONELLA_ENABLED,
    CONF_LEGIONELLA_HOLD,
    CONF_LEGIONELLA_INTERVAL,
    CONF_LEGIONELLA_TARGET,
    CONF_LEGIONELLA_WINDOW_END,
    CONF_LEGIONELLA_WINDOW_START,
    CONF_MODEL,
    CONF_PORT,
    CONF_PV_BATTERY_SENSOR,
    CONF_PV_BATTERY_SIGN,
    CONF_PV_BATTERY_SOC_LIMIT,
    CONF_PV_BATTERY_SOC_SENSOR,
    CONF_PV_BOOST_ONLY_NEGATIVE_PRICE,
    CONF_PV_COLDSTART,
    CONF_PV_COLDSTART_DELTA,
    CONF_PV_MIN_RUN,
    CONF_PV_DEBOUNCE,
    CONF_PV_ESCALATION,
    CONF_PV_HEATER_POWER,
    CONF_PV_HIGH,
    CONF_PV_HOLD,
    CONF_PV_MAX_STARTS,
    CONF_PV_MIN_OFF,
    CONF_PV_MODE,
    CONF_PV_MORNING_ENABLED,
    CONF_PV_MORNING_TIME,
    CONF_PV_NEGATIVE_PRICE_SENSOR,
    CONF_PV_POWER_ENTITY,
    CONF_PV_PRIORITY_LOCK,
    CONF_PV_SENSOR,
    CONF_PV_TEMP_BASE,
    CONF_PV_TEMP_HIGH,
    CONF_PV_TEMP_NORMAL,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL_PORT,
    CONF_SLAVE,
    CONNECTION_SERIAL,
    CONNECTION_TCP,
    DEFAULT_AMBIENT_OFFSET,
    DEFAULT_BAUDRATE,
    DEFAULT_CONNECTION_TYPE,
    DEFAULT_DASHBOARD_ENABLED,
    DEFAULT_HEAT_EXCHANGER,
    HEAT_EXCHANGER_OPTIONS,
    DEFAULT_EMERGENCY_CRITICAL,
    DEFAULT_EMERGENCY_MODE,
    DEFAULT_EMERGENCY_RECOVER,
    DEFAULT_ENERGY_SCALE,
    DEFAULT_LEGIONELLA_BOTTOM,
    DEFAULT_LEGIONELLA_HOLD,
    DEFAULT_LEGIONELLA_INTERVAL,
    DEFAULT_LEGIONELLA_TARGET,
    DEFAULT_LEGIONELLA_WINDOW_END,
    DEFAULT_LEGIONELLA_WINDOW_START,
    DEFAULT_MODEL_KEY,
    DEFAULT_PORT,
    DEFAULT_PV_BATTERY_SIGN,
    DEFAULT_PV_BATTERY_SOC_LIMIT,
    DEFAULT_PV_BOOST_ONLY_NEGATIVE_PRICE,
    DEFAULT_PV_COLDSTART,
    DEFAULT_PV_COLDSTART_DELTA,
    DEFAULT_PV_MIN_RUN,
    DEFAULT_PV_DEBOUNCE,
    DEFAULT_PV_ESCALATION,
    DEFAULT_PV_HEATER_POWER,
    DEFAULT_PV_HIGH,
    DEFAULT_PV_HOLD,
    DEFAULT_PV_MAX_STARTS,
    DEFAULT_PV_MIN_OFF,
    DEFAULT_PV_MODE,
    DEFAULT_PV_MORNING_ENABLED,
    DEFAULT_PV_MORNING_TIME,
    DEFAULT_PV_TEMP_BASE,
    DEFAULT_PV_TEMP_HIGH,
    DEFAULT_PV_TEMP_NORMAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DOMAIN,
    EMERGENCY_MODE_AUTO,
    EMERGENCY_MODE_ELEC,
    MODELS,
    PV_ESC_BOOST,
    PV_ESC_NONE,
    PV_MODE_COORDINATOR,
    PV_MODE_EXECUTOR,
    PV_MODE_OFF,
    READ_START,
    SET_TEMP_MAX,
    SET_TEMP_MIN,
    WP_MAX_TEMP,
    localized_title,
)
from .modbus_client import connection_settings, create_client, unit_kwargs

_LOGGER = logging.getLogger(__name__)

_ENERGY_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
)
_PV_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power")
)
# Negativpreis-Kennung: üblicherweise ein Template-binary_sensor (Tibber/aWATTar/
# Nordpool); input_boolean bewusst zugelassen (manuelles Umschalten/Test).
_NEGATIVE_PRICE_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean"])
)
# Optionale Geräte-Gesamtleistung (W) – Verfeinerung der Heizstab-Leistungsschätzung (AP3).
_POWER_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power")
)
# Vorrang anderer Senken (v1.20.0): Akku-Leistung (W) + Vorzeichen, Ladestand (%),
# Vorrang-Sperre. ``switch`` bei der Sperre bewusst zugelassen (z. B. Wallbox-Schalter).
_BATTERY_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power")
)
_BATTERY_SIGN = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[BATTERY_SIGN_CHARGE_POSITIVE, BATTERY_SIGN_CHARGE_NEGATIVE],
        translation_key="pv_battery_sign",
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
_SOC_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="battery")
)
_PERCENT = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="%",
                                  mode=selector.NumberSelectorMode.BOX)
)
_PRIORITY_LOCK = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean", "switch"])
)
_ESCALATION = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[PV_ESC_NONE, PV_ESC_BOOST],
        translation_key="pv_escalation",
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
_EMERGENCY_MODE = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[EMERGENCY_MODE_AUTO, EMERGENCY_MODE_ELEC],
        translation_key="emergency_mode",
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
_PV_MODE = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[PV_MODE_OFF, PV_MODE_COORDINATOR, PV_MODE_EXECUTOR],
        translation_key="pv_mode",
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
_TIME = selector.TimeSelector()
_SCALE = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0.001, max=1000, step=0.001, mode=selector.NumberSelectorMode.BOX)
)
_MODEL = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=list(MODELS.keys()),
        translation_key="model",
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
# Einmalige Dashboard-Aktionen im Options-Schritt „Dashboard“ (nicht gespeichert).
_DASH_ACTION = "dashboard_action"
_DASH_ACTION_NONE = "none"
_DASH_ACTION_COMPARE = "compare"
_DASH_ACTION_PROMOTE = "promote"
_DASH_ACTION_REPLACE = "replace"

_CONNECTION_TYPE = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[CONNECTION_TCP, CONNECTION_SERIAL],
        translation_key="connection_type",
        mode=selector.SelectSelectorMode.LIST,
    )
)
_BAUDRATE = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=["9600", "19200", "38400"],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
_WATT = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=10000, step=50, unit_of_measurement="W",
                                  mode=selector.NumberSelectorMode.BOX)
)
_TEMP = selector.NumberSelector(
    selector.NumberSelectorConfig(min=SET_TEMP_MIN, max=SET_TEMP_MAX, step=1,
                                  unit_of_measurement="°C", mode=selector.NumberSelectorMode.SLIDER)
)
# Zieltemperaturen, die der **Verdichter allein** erreichen muss (Normal/Erhöht), sind auf
# WP_MAX_TEMP begrenzt – darüber käme nur der Heizstab, was auf diesen Stufen nicht
# vorgesehen ist. Nur die Boost-Zieltemperatur darf bis SET_TEMP_MAX (mit Heizstab).
_TEMP_WP = selector.NumberSelector(
    selector.NumberSelectorConfig(min=SET_TEMP_MIN, max=WP_MAX_TEMP, step=1,
                                  unit_of_measurement="°C", mode=selector.NumberSelectorMode.SLIDER)
)
_OFFSET = selector.NumberSelector(
    selector.NumberSelectorConfig(min=-15, max=15, step=0.1,
                                  unit_of_measurement="°C", mode=selector.NumberSelectorMode.BOX)
)
_DAYS = selector.NumberSelector(
    selector.NumberSelectorConfig(min=1, max=30, step=1,
                                  unit_of_measurement="d", mode=selector.NumberSelectorMode.BOX)
)
_MINUTES = selector.NumberSelector(
    selector.NumberSelectorConfig(min=1, max=180, step=1,
                                  unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX)
)
# Tageskontingent für von der Leiter ausgelöste Starts (Morgen-Start + Kaltstart, AP6a).
_KELVIN = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0, max=30, step=1, unit_of_measurement="K",
                                  mode=selector.NumberSelectorMode.SLIDER)
)
_STARTS = selector.NumberSelector(
    selector.NumberSelectorConfig(min=1, max=5, step=1, mode=selector.NumberSelectorMode.BOX)
)


def _cop_schema(o: dict[str, Any], expert: bool = False) -> vol.Schema:
    """COP-/Energiequellen-Schema.

    Die Quelle ergibt sich aus der gewählten Entität: leer = integriertes
    Modbus-Register, gesetzt = externer Zähler. Kein separates Quellen-Dropdown.
    Register-Skalierung und Bezugsdatum sind Expertenfelder und erscheinen nur
    in den Optionen (``expert=True``), nicht in der Ersteinrichtung.
    """
    fields: dict[Any, Any] = {
        vol.Optional(CONF_COP_ENABLED, default=o.get(CONF_COP_ENABLED, True)): bool,
        vol.Optional(CONF_COP_ELEC_ENTITY): _ENERGY_ENTITY,
        vol.Optional(CONF_COP_HEAT_ENTITY): _ENERGY_ENTITY,
    }
    if expert:
        fields[vol.Optional(CONF_ENERGY_SCALE,
                            default=o.get(CONF_ENERGY_SCALE, DEFAULT_ENERGY_SCALE))] = _SCALE
        fields[vol.Optional(CONF_COP_REF_DATE)] = selector.DateSelector()
    return vol.Schema(fields)


def _protection_schema(o: dict[str, Any], full: bool) -> vol.Schema:
    """Schutzfunktionen: Notfall-Nachheizung + Legionellen-Schutz.

    Ersteinrichtung (``full=False``): nur die beiden Schalter mit sinnvollen
    Standardwerten; alle Schwellen und Zeiten in den Optionen.
    """
    fields: dict[Any, Any] = {
        # Ersteinrichtung: empfohlen an. Optionen: fehlender Key = aus (wie emergency.py),
        # sonst würde Speichern die Notheizung still einschalten.
        vol.Optional(CONF_EMERGENCY_ENABLED, default=o.get(CONF_EMERGENCY_ENABLED, not full)): bool,
    }
    if full:
        fields.update({
            vol.Optional(CONF_EMERGENCY_CRITICAL,
                         default=o.get(CONF_EMERGENCY_CRITICAL, DEFAULT_EMERGENCY_CRITICAL)): _TEMP,
            vol.Optional(CONF_EMERGENCY_RECOVER,
                         default=o.get(CONF_EMERGENCY_RECOVER, DEFAULT_EMERGENCY_RECOVER)): _TEMP,
            vol.Optional(CONF_EMERGENCY_MODE,
                         default=o.get(CONF_EMERGENCY_MODE, DEFAULT_EMERGENCY_MODE)): _EMERGENCY_MODE,
        })
    fields[vol.Optional(CONF_LEGIONELLA_ENABLED,
                        default=o.get(CONF_LEGIONELLA_ENABLED, False))] = bool
    if full:
        fields.update({
            # W3: Verdichtergrenze (_TEMP_WP, max WP_MAX_TEMP), nicht die Registergrenze
            # – der Lauf eskaliert auf AUTO (reine WP); das Abbruchkriterium ist bottom_min.
            vol.Optional(CONF_LEGIONELLA_TARGET,
                         default=o.get(CONF_LEGIONELLA_TARGET, DEFAULT_LEGIONELLA_TARGET)): _TEMP_WP,
            vol.Optional(CONF_LEGIONELLA_INTERVAL,
                         default=o.get(CONF_LEGIONELLA_INTERVAL, DEFAULT_LEGIONELLA_INTERVAL)): _DAYS,
            vol.Optional(CONF_LEGIONELLA_BOTTOM,
                         default=o.get(CONF_LEGIONELLA_BOTTOM, DEFAULT_LEGIONELLA_BOTTOM)): _TEMP,
            vol.Optional(CONF_LEGIONELLA_HOLD,
                         default=o.get(CONF_LEGIONELLA_HOLD, DEFAULT_LEGIONELLA_HOLD)): _MINUTES,
            vol.Optional(CONF_LEGIONELLA_WINDOW_START,
                         default=o.get(CONF_LEGIONELLA_WINDOW_START, DEFAULT_LEGIONELLA_WINDOW_START)): _TIME,
            vol.Optional(CONF_LEGIONELLA_WINDOW_END,
                         default=o.get(CONF_LEGIONELLA_WINDOW_END, DEFAULT_LEGIONELLA_WINDOW_END)): _TIME,
        })
    return vol.Schema(fields)


def _pv_mode_schema(o: dict[str, Any]) -> vol.Schema:
    """Nur das **PV-Modus**-Dropdown (Aus/Coordinator/Executor).

    Erster Schritt eines zweistufigen Dialogs: zuerst der Modus, danach (eigener
    Schritt ``_pv_detail_schema``) genau die Felder des gewählten Modus – so sind
    nie irrelevante Felder sichtbar.
    """
    return vol.Schema(
        {vol.Optional(CONF_PV_MODE, default=o.get(CONF_PV_MODE, DEFAULT_PV_MODE)): _PV_MODE}
    )


# Abschnitte der PV-Details (Coordinator): oben die Kernfelder, darunter einklappbar.
SECTION_BATTERY = "battery"
SECTION_HEATER = "heater"
SECTION_TIMING = "timing"
_PV_SECTIONS = (SECTION_BATTERY, SECTION_HEATER, SECTION_TIMING)


def _pv_detail_schema(o: dict[str, Any], mode: str) -> vol.Schema:
    """Modus-spezifische PV-Felder (zweiter Schritt).

    - **Coordinator:** oben PV-Sensor und die beiden Zieltemperaturen, darunter
      einklappbare Abschnitte *Hausakku & Vorrang*, *Heizstab & Strompreis* und
      *Zeiten & Starts (Experte)* – sonst wären es 24 Felder auf einer Seite.
      Werte kommen je Abschnitt verschachtelt zurück (``_flatten``).
    - **Executor:** nur die Zieltemps (Mechanik fürs Programm-Select); geregelt
      wird über ``select.haier_hwhp_pv_program`` durch das HEMS.
    - **Aus:** keine Felder (der Schritt wird übersprungen).
    """
    temps = {
        vol.Optional(CONF_PV_TEMP_BASE, default=o.get(CONF_PV_TEMP_BASE, DEFAULT_PV_TEMP_BASE)): _TEMP_WP,
        vol.Optional(CONF_PV_TEMP_NORMAL,
                     default=o.get(CONF_PV_TEMP_NORMAL, DEFAULT_PV_TEMP_NORMAL)): _TEMP_WP,
    }
    if mode == PV_MODE_EXECUTOR:
        # Boost-Zieltemperatur nur noch für das Executor-Programm (PV_PROGRAM_BOOST).
        return vol.Schema({
            **temps,
            vol.Optional(CONF_PV_TEMP_HIGH,
                         default=o.get(CONF_PV_TEMP_HIGH, DEFAULT_PV_TEMP_HIGH)): _TEMP,
        })
    if mode != PV_MODE_COORDINATOR:
        return vol.Schema({})

    battery = vol.Schema({
        vol.Optional(CONF_PV_BATTERY_SENSOR): _BATTERY_SENSOR,
        vol.Optional(CONF_PV_BATTERY_SIGN,
                     default=o.get(CONF_PV_BATTERY_SIGN, DEFAULT_PV_BATTERY_SIGN)): _BATTERY_SIGN,
        vol.Optional(CONF_PV_BATTERY_SOC_SENSOR): _SOC_SENSOR,
        vol.Optional(CONF_PV_BATTERY_SOC_LIMIT,
                     default=o.get(CONF_PV_BATTERY_SOC_LIMIT, DEFAULT_PV_BATTERY_SOC_LIMIT)): _PERCENT,
        vol.Optional(CONF_PV_PRIORITY_LOCK): _PRIORITY_LOCK,
    })
    heater = vol.Schema({
        vol.Optional(CONF_PV_ESCALATION,
                     default=o.get(CONF_PV_ESCALATION, DEFAULT_PV_ESCALATION)): _ESCALATION,
        vol.Optional(CONF_PV_HIGH, default=o.get(CONF_PV_HIGH, DEFAULT_PV_HIGH)): _WATT,
        vol.Optional(CONF_PV_HEATER_POWER,
                     default=o.get(CONF_PV_HEATER_POWER, DEFAULT_PV_HEATER_POWER)): _WATT,
        vol.Optional(CONF_PV_POWER_ENTITY): _POWER_ENTITY,
        vol.Optional(CONF_PV_BOOST_ONLY_NEGATIVE_PRICE,
                     default=o.get(CONF_PV_BOOST_ONLY_NEGATIVE_PRICE,
                                   DEFAULT_PV_BOOST_ONLY_NEGATIVE_PRICE)): bool,
        vol.Optional(CONF_PV_NEGATIVE_PRICE_SENSOR): _NEGATIVE_PRICE_SENSOR,
    })
    timing = vol.Schema({
        vol.Optional(CONF_PV_MORNING_ENABLED,
                     default=o.get(CONF_PV_MORNING_ENABLED, DEFAULT_PV_MORNING_ENABLED)): bool,
        vol.Optional(CONF_PV_MORNING_TIME,
                     default=o.get(CONF_PV_MORNING_TIME, DEFAULT_PV_MORNING_TIME)): _TIME,
        vol.Optional(CONF_PV_COLDSTART, default=o.get(CONF_PV_COLDSTART, DEFAULT_PV_COLDSTART)): _WATT,
        vol.Optional(CONF_PV_COLDSTART_DELTA,
                     default=o.get(CONF_PV_COLDSTART_DELTA, DEFAULT_PV_COLDSTART_DELTA)): _KELVIN,
        vol.Optional(CONF_PV_HOLD, default=o.get(CONF_PV_HOLD, DEFAULT_PV_HOLD)): _WATT,
        vol.Optional(CONF_PV_MIN_RUN, default=o.get(CONF_PV_MIN_RUN, DEFAULT_PV_MIN_RUN)): _MINUTES,
        vol.Optional(CONF_PV_MAX_STARTS, default=o.get(CONF_PV_MAX_STARTS, DEFAULT_PV_MAX_STARTS)): _STARTS,
        vol.Optional(CONF_PV_DEBOUNCE, default=o.get(CONF_PV_DEBOUNCE, DEFAULT_PV_DEBOUNCE)): int,
        vol.Optional(CONF_PV_MIN_OFF, default=o.get(CONF_PV_MIN_OFF, DEFAULT_PV_MIN_OFF)): int,
    })
    return vol.Schema({
        vol.Optional(CONF_PV_SENSOR): _PV_SENSOR,
        **temps,
        vol.Required(SECTION_BATTERY): section(battery, {"collapsed": True}),
        vol.Required(SECTION_HEATER): section(heater, {"collapsed": True}),
        vol.Required(SECTION_TIMING): section(timing, {"collapsed": True}),
    })


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    """Abschnitts-Werte (verschachtelt) flach machen; leere Werte entfernen."""
    flat: dict[str, Any] = {}
    for key, val in user_input.items():
        if key in _PV_SECTIONS and isinstance(val, dict):
            flat.update(val)
        else:
            flat[key] = val
    return {k: v for k, v in flat.items() if v not in ("", None)}


def _nest(values: dict[str, Any], schema: vol.Schema) -> dict[str, Any]:
    """Flache Werte für ``add_suggested_values_to_schema`` in Abschnitte einsortieren."""
    out = dict(values)
    for key, val in schema.schema.items():
        if isinstance(val, section):
            out[str(key)] = {str(k): values[str(k)] for k in val.schema.schema if str(k) in values}
    return out


def _schema_keys(schema: vol.Schema) -> set[str]:
    """Alle Feldnamen eines Schemas, Abschnitte aufgelöst."""
    keys: set[str] = set()
    for key, val in schema.schema.items():
        if isinstance(val, section):
            keys |= {str(k) for k in val.schema.schema}
        else:
            keys.add(str(key))
    return keys


def _temp_order_error(merged: dict[str, Any]) -> str | None:
    """Plausibilität der PV-Zieltemperaturen: Normal < Erhöht ≤ Boost-Zieltemperatur.

    Ohne echte Staffelung kollabieren die Regelstufen: Ist Erhöht nicht höher als
    Normal, gibt es keine Zwischenstufe mehr. Die Boost-Zieltemperatur (``pv_temp_high``)
    ist seit v1.16.0 nur noch für das Executor-Programm „Boost" relevant – im
    Coordinator-Modus nutzt Boost dieselbe Zieltemperatur wie Erhöht, die Reihenfolge
    bleibt aber auch dort sinnvoll (verhindert eine verdrehte Konfiguration beim
    Moduswechsel). ``pv.py`` klemmt verdrehte Werte zwar zur Laufzeit ab, aber ein
    Hinweis beim Speichern ist ehrlicher als eine stillschweigende Korrektur.
    """
    base = merged.get(CONF_PV_TEMP_BASE, DEFAULT_PV_TEMP_BASE)
    normal = merged.get(CONF_PV_TEMP_NORMAL, DEFAULT_PV_TEMP_NORMAL)
    high = merged.get(CONF_PV_TEMP_HIGH, DEFAULT_PV_TEMP_HIGH)
    try:
        base, normal, high = float(base), float(normal), float(high)
    except (TypeError, ValueError):
        return None
    if normal <= base:
        return "temp_order_normal"
    if high < normal:
        return "temp_order_high"
    return None


def _pv_coordinator_error(merged: dict[str, Any]) -> str | None:
    """Zusätzliche Plausibilität für den Coordinator-Modus (AP7):

    - ``pv_high`` muss die Heizstab-Nennleistung + 50 W decken – sonst schaltet der
      Heizstab in den Netzbezug hinein ab. Die Laufzeit-Klemme in ``pv.py`` bleibt
      als zweites Netz bestehen (falls die Heizstab-Leistung später geändert wird).
    """
    try:
        pv_high = float(merged.get(CONF_PV_HIGH, DEFAULT_PV_HIGH))
        heater_power = float(merged.get(CONF_PV_HEATER_POWER, DEFAULT_PV_HEATER_POWER))
    except (TypeError, ValueError):
        return None
    if pv_high < heater_power + 50:
        return "pv_high_too_low"
    return None


_BY_ID_DIR = "/dev/serial/by-id"


def _list_serial_ports() -> list[str]:
    """Serielle Ports zur Auswahl (blockierend -> im Executor aufrufen).

    Bevorzugt die stabilen ``/dev/serial/by-id/...``-Pfade (ändern sich nicht,
    wenn mehrere USB-Adapter umnummeriert werden), danach die übrigen Geräte.
    Fehlt pyserial oder das Verzeichnis, bleibt die Liste leer – der Pfad kann
    dann frei eingetragen werden.
    """
    ports: list[str] = []
    try:
        ports += sorted(
            os.path.join(_BY_ID_DIR, name) for name in os.listdir(_BY_ID_DIR)
        )
    except OSError:
        pass
    try:
        from serial.tools import list_ports  # pyserial

        ports += [p.device for p in list_ports.comports() if p.device not in ports]
    except Exception:  # noqa: BLE001
        pass
    return ports


def _serial_port_selector(ports: list[str]):
    """Auswahlliste mit freier Eingabe; ohne gefundene Ports ein Textfeld."""
    if not ports:
        return str
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=ports,
            custom_value=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


async def _test_connection(settings: dict[str, Any], slave: int) -> bool:
    """Kurzer Verbindungstest (ein Register lesen) – TCP-Konverter oder seriell."""
    client = create_client(settings)
    try:
        await client.connect()
        if not client.connected:
            return False
        method = client.read_holding_registers
        rr = await method(READ_START, count=1, **unit_kwargs(method, slave))
        return not rr.isError()
    except Exception:  # noqa: BLE001
        return False
    finally:
        client.close()


class HaierModbusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Einrichtungsassistent: Verbindungsart -> TCP/seriell -> COP -> PV."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._cop: dict[str, Any] = {}
        self._pv: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Verbindungsart wählen: TCP-Konverter (Bestand) oder seriell (#16)."""
        if user_input is not None:
            if user_input.get(CONF_CONNECTION_TYPE) == CONNECTION_SERIAL:
                return await self.async_step_serial()
            return await self.async_step_tcp()
        schema = vol.Schema(
            {
                vol.Required(CONF_CONNECTION_TYPE, default=DEFAULT_CONNECTION_TYPE): _CONNECTION_TYPE,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input.get(CONF_PORT, DEFAULT_PORT)}"
            )
            self._abort_if_unique_id_configured()
            settings = {CONF_CONNECTION_TYPE: CONNECTION_TCP, **user_input}
            ok = await _test_connection(
                connection_settings({}, settings),
                user_input.get(CONF_SLAVE, DEFAULT_SLAVE),
            )
            if not ok:
                errors["base"] = "cannot_connect"
            else:
                self._data = settings
                return await self.async_step_cop()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_SLAVE, default=DEFAULT_SLAVE): int,
                vol.Required(CONF_MODEL, default=DEFAULT_MODEL_KEY): _MODEL,
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="tcp", data_schema=schema, errors=errors)

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Direkt per USB/RS-485-Adapter (Modbus RTU, 8N1)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = {**user_input, CONF_BAUDRATE: int(user_input.get(CONF_BAUDRATE, DEFAULT_BAUDRATE))}
            await self.async_set_unique_id(f"serial:{user_input[CONF_SERIAL_PORT]}")
            self._abort_if_unique_id_configured()
            settings = {CONF_CONNECTION_TYPE: CONNECTION_SERIAL, **user_input}
            ok = await _test_connection(
                connection_settings({}, settings),
                user_input.get(CONF_SLAVE, DEFAULT_SLAVE),
            )
            if not ok:
                errors["base"] = "cannot_connect_serial"
            else:
                self._data = settings
                return await self.async_step_cop()

        ports = await self.hass.async_add_executor_job(_list_serial_ports)
        schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL_PORT): _serial_port_selector(ports),
                vol.Required(CONF_BAUDRATE, default=str(DEFAULT_BAUDRATE)): _BAUDRATE,
                vol.Required(CONF_SLAVE, default=DEFAULT_SLAVE): int,
                vol.Required(CONF_MODEL, default=DEFAULT_MODEL_KEY): _MODEL,
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(
                schema, {**user_input, CONF_BAUDRATE: str(user_input[CONF_BAUDRATE])}
            )
        return self.async_show_form(step_id="serial", data_schema=schema, errors=errors)

    async def async_step_cop(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            self._cop = {k: v for k, v in user_input.items() if v not in ("", None)}
            return await self.async_step_protection()
        return self.async_show_form(step_id="cop", data_schema=_cop_schema({}))

    async def async_step_protection(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Schutzfunktionen (Notfall-Nachheizung, Legionellen) – nur die Schalter."""
        if user_input is not None:
            self._cop.update(user_input)
            return await self.async_step_pv()
        return self.async_show_form(step_id="protection", data_schema=_protection_schema({}, full=False))

    async def async_step_pv(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Schritt 1: PV-Modus wählen. Bei „Aus“ direkt fertig, sonst Detail-Schritt."""
        if user_input is not None:
            self._pv = {k: v for k, v in user_input.items() if v not in ("", None)}
            if self._pv.get(CONF_PV_MODE, DEFAULT_PV_MODE) == PV_MODE_OFF:
                return self._create_entry()
            return await self.async_step_pv_details()
        return self.async_show_form(step_id="pv", data_schema=_pv_mode_schema({}))

    async def async_step_pv_details(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Schritt 2: genau die Felder des in Schritt 1 gewählten Modus."""
        errors: dict[str, str] = {}
        mode = self._pv.get(CONF_PV_MODE, DEFAULT_PV_MODE)
        if user_input is not None:
            details = _flatten(user_input)
            merged = {**self._pv, **details}
            if mode == PV_MODE_COORDINATOR and not merged.get(CONF_PV_SENSOR):
                errors["base"] = "pv_sensor_required"
            elif (order_error := _temp_order_error(merged)) is not None:
                errors["base"] = order_error
            elif mode == PV_MODE_COORDINATOR and (coord_error := _pv_coordinator_error(merged)) is not None:
                errors["base"] = coord_error
            else:
                self._pv = merged
                return self._create_entry()

        schema = _pv_detail_schema(self._pv, mode)
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, _nest(_flatten(user_input), schema))
        return self.async_show_form(step_id="pv_details", data_schema=schema, errors=errors)

    def _create_entry(self) -> config_entries.ConfigFlowResult:
        return self.async_create_entry(
            title=localized_title(self.hass.config.language),
            data=self._data,
            options={**self._cop, **self._pv},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "HaierModbusOptionsFlow":
        return HaierModbusOptionsFlow()


class HaierModbusOptionsFlow(config_entries.OptionsFlow):
    """Optionen als Menü: Verbindung · Energie & COP · PV · Schutzfunktionen · Dashboard.

    Jeder Bereich speichert nur seine eigenen Felder und übernimmt alle übrigen
    Optionen unverändert (``_save``). Leere Felder entfernen den Wert (z. B. eine
    abgewählte Entität).
    """

    _pv_mode: str = DEFAULT_PV_MODE
    _conn_type: str = DEFAULT_CONNECTION_TYPE

    def _cur(self, key: str, default: Any) -> Any:
        return self.config_entry.options.get(key, self.config_entry.data.get(key, default))

    def _save(self, schema: vol.Schema, values: dict[str, Any]) -> config_entries.ConfigFlowResult:
        keys = _schema_keys(schema)
        merged = {k: v for k, v in self.config_entry.options.items() if k not in keys}
        merged.update(values)
        return self.async_create_entry(title="", data=merged)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["connection", "energy", "pv_mode", "protection", "dashboard"],
        )

    def _device_fields(self) -> dict:
        """Felder, die für beide Verbindungsarten gelten."""
        return {
            vol.Optional(CONF_SLAVE, default=self._cur(CONF_SLAVE, DEFAULT_SLAVE)): int,
            vol.Optional(CONF_MODEL, default=self._cur(CONF_MODEL, DEFAULT_MODEL_KEY)): _MODEL,
            vol.Optional(CONF_SCAN_INTERVAL,
                         default=self._cur(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): int,
            vol.Optional(CONF_AMBIENT_OFFSET,
                         default=self._cur(CONF_AMBIENT_OFFSET, DEFAULT_AMBIENT_OFFSET)): _OFFSET,
        }

    async def async_step_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Verbindung, Schritt 1: nur die Art – danach erscheinen nur deren Felder.

        HA-Formulare sind statisch (Felder lassen sich nicht abhängig von einer
        Auswahl ein-/ausblenden), daher zwei Schritte wie im Einrichtungsassistenten.
        """
        if user_input is not None:
            self._conn_type = user_input.get(CONF_CONNECTION_TYPE, DEFAULT_CONNECTION_TYPE)
            if self._conn_type == CONNECTION_SERIAL:
                return await self.async_step_connection_serial()
            return await self.async_step_connection_tcp()
        schema = vol.Schema({
            vol.Required(CONF_CONNECTION_TYPE,
                         default=self._cur(CONF_CONNECTION_TYPE, DEFAULT_CONNECTION_TYPE)): _CONNECTION_TYPE,
        })
        return self.async_show_form(step_id="connection", data_schema=schema)

    async def async_step_connection_tcp(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        schema = vol.Schema({
            vol.Optional(CONF_HOST, default=self._cur(CONF_HOST, "")): str,
            vol.Optional(CONF_PORT, default=self._cur(CONF_PORT, DEFAULT_PORT)): int,
            **self._device_fields(),
        })
        if user_input is not None:
            values = {k: v for k, v in user_input.items() if v not in ("", None)}
            if not connection_settings(values, self.config_entry.data)[CONF_HOST]:
                errors["base"] = "host_required"
            else:
                return self._save(
                    schema.extend({vol.Optional(CONF_CONNECTION_TYPE): str}),
                    {**values, CONF_CONNECTION_TYPE: CONNECTION_TCP},
                )
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="connection_tcp", data_schema=schema, errors=errors)

    async def async_step_connection_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        ports = await self.hass.async_add_executor_job(_list_serial_ports)
        cur_port = self._cur(CONF_SERIAL_PORT, "")
        if cur_port and cur_port not in ports:
            ports = [cur_port, *ports]
        schema = vol.Schema({
            vol.Optional(CONF_SERIAL_PORT, default=cur_port): _serial_port_selector(ports),
            vol.Optional(CONF_BAUDRATE,
                         default=str(self._cur(CONF_BAUDRATE, DEFAULT_BAUDRATE))): _BAUDRATE,
            **self._device_fields(),
        })
        if user_input is not None:
            values = {k: v for k, v in user_input.items() if v not in ("", None)}
            if CONF_BAUDRATE in values:
                values[CONF_BAUDRATE] = int(values[CONF_BAUDRATE])
            if not connection_settings(
                {**values, CONF_CONNECTION_TYPE: CONNECTION_SERIAL}, self.config_entry.data
            )[CONF_SERIAL_PORT]:
                errors["base"] = "serial_port_required"
            else:
                return self._save(
                    schema.extend({vol.Optional(CONF_CONNECTION_TYPE): str}),
                    {**values, CONF_CONNECTION_TYPE: CONNECTION_SERIAL},
                )
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="connection_serial", data_schema=schema, errors=errors)

    async def async_step_energy(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        o = self.config_entry.options
        schema = _cop_schema(o, expert=True)
        if user_input is not None:
            return self._save(schema, {k: v for k, v in user_input.items() if v not in ("", None)})
        return self.async_show_form(
            step_id="energy", data_schema=self.add_suggested_values_to_schema(schema, o)
        )

    async def async_step_protection(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        schema = _protection_schema(self.config_entry.options, full=True)
        if user_input is not None:
            return self._save(schema, {k: v for k, v in user_input.items() if v not in ("", None)})
        return self.async_show_form(step_id="protection", data_schema=schema)

    async def async_step_dashboard(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Dashboard an/aus + einmalige Aktionen (Vergleich anlegen/übernehmen, ersetzen).

        Die Aktion wird nicht in den Optionen gespeichert. Ändert sich nur sie, endet
        der Dialog ohne Speichern – sonst würde ein Options-Update die Integration neu
        laden (und dabei In-Memory-Zustände der Regler verwerfen).
        """
        from .dashboard import (  # lokal: zieht Frontend-Module erst bei Bedarf
            LAYOUT_STATUS_KEY,
            async_create_compare_dashboard,
            async_promote_compare_dashboard,
            async_rebuild_dashboard,
        )

        from .dashboard_layout import IMAGE_URL_RE

        status = self.hass.data.get(LAYOUT_STATUS_KEY) or {}
        actions = [_DASH_ACTION_NONE, _DASH_ACTION_COMPARE]
        if status.get("compare"):
            actions.append(_DASH_ACTION_PROMOTE)
        actions.append(_DASH_ACTION_REPLACE)
        enabled = self._cur(CONF_DASHBOARD_ENABLED, DEFAULT_DASHBOARD_ENABLED)
        hx = self._cur(CONF_HEAT_EXCHANGER, DEFAULT_HEAT_EXCHANGER)
        image = self._cur(CONF_DASHBOARD_IMAGE, "")
        saved_schema = vol.Schema({
            vol.Optional(CONF_DASHBOARD_ENABLED): bool,
            vol.Optional(CONF_HEAT_EXCHANGER): str,
            vol.Optional(CONF_DASHBOARD_IMAGE): str,
        })
        schema = vol.Schema({
            vol.Optional(CONF_DASHBOARD_ENABLED, default=enabled): bool,
            vol.Optional(CONF_HEAT_EXCHANGER, default=hx): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=HEAT_EXCHANGER_OPTIONS,
                    translation_key="heat_exchanger",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            # Leer = eigene Zeichnung; „suggested_value“, damit das Feld leerbar bleibt.
            vol.Optional(CONF_DASHBOARD_IMAGE, description={"suggested_value": image}):
                selector.TextSelector(),
            vol.Optional(_DASH_ACTION, default=_DASH_ACTION_NONE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=actions,
                    translation_key="dashboard_action",
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        })
        errors: dict[str, str] = {}
        if user_input is not None:
            action = user_input.get(_DASH_ACTION, _DASH_ACTION_NONE)
            new_vals = {
                CONF_DASHBOARD_ENABLED: user_input.get(CONF_DASHBOARD_ENABLED, enabled),
                CONF_HEAT_EXCHANGER: user_input.get(CONF_HEAT_EXCHANGER, hx),
                CONF_DASHBOARD_IMAGE: (user_input.get(CONF_DASHBOARD_IMAGE) or "").strip(),
            }
            changed = new_vals != {CONF_DASHBOARD_ENABLED: enabled,
                                   CONF_HEAT_EXCHANGER: hx, CONF_DASHBOARD_IMAGE: image}
            if new_vals[CONF_DASHBOARD_IMAGE] and not IMAGE_URL_RE.match(new_vals[CONF_DASHBOARD_IMAGE]):
                errors[CONF_DASHBOARD_IMAGE] = "dashboard_image_invalid"
            elif action != _DASH_ACTION_NONE and not new_vals[CONF_DASHBOARD_ENABLED]:
                errors["base"] = "dashboard_disabled"
            elif action == _DASH_ACTION_NONE:
                if changed:
                    # Reload -> Layout-Abgleich: ein unverändertes Dashboard übernimmt
                    # die neue Grafik still, ein angepasstes bekommt den Reparatur-Hinweis.
                    return self._save(saved_schema, new_vals)
                return self.async_abort(reason="dashboard_none")
            else:
                if changed:
                    # Erst speichern, damit die Aktion das neue Bild/die neue Option nutzt.
                    merged = {**self.config_entry.options, **new_vals}
                    self.hass.config_entries.async_update_entry(self.config_entry, options=merged)
                handler = {
                    _DASH_ACTION_COMPARE: async_create_compare_dashboard,
                    _DASH_ACTION_PROMOTE: async_promote_compare_dashboard,
                    _DASH_ACTION_REPLACE: async_rebuild_dashboard,
                }.get(action)
                try:
                    if handler is not None:
                        await handler(self.hass, self.config_entry)
                except Exception:  # noqa: BLE001 – Grund steht im Log
                    _LOGGER.exception("Dashboard-Aktion %s fehlgeschlagen", action)
                    errors["base"] = "dashboard_action_failed"
                else:
                    return self.async_abort(reason=f"dashboard_{action}")
        return self.async_show_form(step_id="dashboard", data_schema=schema, errors=errors)

    async def async_step_pv_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """PV Schritt 1: Modus. Bei „Aus“ direkt speichern, sonst Details."""
        schema = _pv_mode_schema(self.config_entry.options)
        if user_input is not None:
            self._pv_mode = user_input.get(CONF_PV_MODE, DEFAULT_PV_MODE)
            if self._pv_mode == PV_MODE_OFF:
                return self._save(schema, {CONF_PV_MODE: PV_MODE_OFF})
            return await self.async_step_pv()
        return self.async_show_form(step_id="pv_mode", data_schema=schema)

    async def async_step_pv(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """PV Schritt 2: genau die Felder des gewählten Modus (Coordinator in Abschnitten)."""
        errors: dict[str, str] = {}
        mode = self._pv_mode
        o = self.config_entry.options
        schema = _pv_detail_schema(o, mode)
        if user_input is not None:
            details = _flatten(user_input)
            merged = {**o, CONF_PV_MODE: mode, **details}
            if mode == PV_MODE_COORDINATOR and not merged.get(CONF_PV_SENSOR):
                errors["base"] = "pv_sensor_required"
            elif (order_error := _temp_order_error(merged)) is not None:
                errors["base"] = order_error
            elif mode == PV_MODE_COORDINATOR and (coord_error := _pv_coordinator_error(merged)) is not None:
                errors["base"] = coord_error
            else:
                keys = _schema_keys(schema) | {CONF_PV_MODE}
                kept = {k: v for k, v in o.items() if k not in keys}
                return self.async_create_entry(title="", data={**kept, CONF_PV_MODE: mode, **details})
            schema = self.add_suggested_values_to_schema(schema, _nest(details, schema))
        else:
            schema = self.add_suggested_values_to_schema(schema, _nest(dict(o), schema))
        return self.async_show_form(step_id="pv", data_schema=schema, errors=errors)
