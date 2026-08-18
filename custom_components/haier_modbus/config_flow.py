"""Config- und Options-Flow – alles über die HA-Oberfläche konfigurierbar.

Einrichtungsassistent in drei Schritten:
  1. user  – Verbindung + Modell (mit Verbindungstest)
  2. cop   – COP-/Energiequellen
  3. pv    – optionale PV-Überschuss-Steuerung (Sensor + Schwellen)

Der Options-Flow ("Konfigurieren") macht später alles davon änderbar –
inklusive Host/Port/Slave des Modbus-Konverters.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from pymodbus.client import AsyncModbusTcpClient

from .const import (
    CONF_AMBIENT_OFFSET,
    CONF_COP_ELEC_ENTITY,
    CONF_COP_ENABLED,
    CONF_COP_HEAT_ENTITY,
    CONF_COP_REF_DATE,
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
    CONF_PV_SENSOR,
    CONF_PV_TEMP_BASE,
    CONF_PV_TEMP_HIGH,
    CONF_PV_TEMP_NORMAL,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    DEFAULT_AMBIENT_OFFSET,
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


def _cop_schema(o: dict[str, Any]) -> vol.Schema:
    """COP-/Energiequellen-Schema – im Wizard und im Options-Flow identisch.

    Die Quelle ergibt sich aus der gewählten Entität: leer = integriertes
    Modbus-Register, gesetzt = externer Zähler. Kein separates Quellen-Dropdown.
    """
    return vol.Schema(
        {
            vol.Optional(CONF_COP_ENABLED, default=o.get(CONF_COP_ENABLED, True)): bool,
            vol.Optional(CONF_COP_ELEC_ENTITY): _ENERGY_ENTITY,
            vol.Optional(CONF_COP_HEAT_ENTITY): _ENERGY_ENTITY,
            vol.Optional(CONF_ENERGY_SCALE, default=o.get(CONF_ENERGY_SCALE, DEFAULT_ENERGY_SCALE)): _SCALE,
            vol.Optional(CONF_COP_REF_DATE): selector.DateSelector(),
        }
    )


def _pv_mode_schema(o: dict[str, Any]) -> vol.Schema:
    """Nur das **PV-Modus**-Dropdown (Aus/Coordinator/Executor).

    Erster Schritt eines zweistufigen Dialogs: zuerst der Modus, danach (eigener
    Schritt ``_pv_detail_schema``) genau die Felder des gewählten Modus – so sind
    nie irrelevante Felder sichtbar.
    """
    return vol.Schema(
        {vol.Optional(CONF_PV_MODE, default=o.get(CONF_PV_MODE, DEFAULT_PV_MODE)): _PV_MODE}
    )


def _pv_detail_schema(o: dict[str, Any], mode: str) -> vol.Schema:
    """Modus-spezifische PV-Felder (zweiter Schritt).

    - **Coordinator:** PV-Sensor, Zieltemps und alle Regel-Schwellen.
    - **Executor:** nur die Zieltemps (Mechanik fürs Programm-Select); geregelt
      wird über ``select.haier_hwhp_pv_program`` durch das HEMS.
    - **Aus:** keine Felder (der Schritt wird übersprungen).
    """
    fields: dict[Any, Any] = {}
    if mode == PV_MODE_COORDINATOR:
        fields[vol.Optional(CONF_PV_SENSOR)] = _PV_SENSOR

    if mode in (PV_MODE_COORDINATOR, PV_MODE_EXECUTOR):
        # Zieltemps sind die gemeinsame Mechanik beider Modi.
        fields.update(
            {
                vol.Optional(CONF_PV_TEMP_NORMAL,
                             default=o.get(CONF_PV_TEMP_NORMAL, DEFAULT_PV_TEMP_NORMAL)): _TEMP_WP,
                vol.Optional(CONF_PV_TEMP_BASE, default=o.get(CONF_PV_TEMP_BASE, DEFAULT_PV_TEMP_BASE)): _TEMP_WP,
            }
        )

    if mode == PV_MODE_EXECUTOR:
        # Nur noch für das Executor-Programm relevant (PV_PROGRAM_BOOST) – im
        # Coordinator ist Boost seit v1.16.0 eine Leistungssenke mit derselben
        # Zieltemperatur wie Erhöht (AP2), dieses Feld dort daher bewusst nicht mehr.
        fields[vol.Optional(CONF_PV_TEMP_HIGH,
                             default=o.get(CONF_PV_TEMP_HIGH, DEFAULT_PV_TEMP_HIGH))] = _TEMP

    if mode == PV_MODE_COORDINATOR:
        fields.update(
            {
                vol.Optional(CONF_PV_HOLD, default=o.get(CONF_PV_HOLD, DEFAULT_PV_HOLD)): _WATT,
                vol.Optional(CONF_PV_HIGH, default=o.get(CONF_PV_HIGH, DEFAULT_PV_HIGH)): _WATT,
                vol.Optional(CONF_PV_HEATER_POWER,
                             default=o.get(CONF_PV_HEATER_POWER, DEFAULT_PV_HEATER_POWER)): _WATT,
                vol.Optional(CONF_PV_POWER_ENTITY): _POWER_ENTITY,
                vol.Optional(CONF_PV_MORNING_ENABLED,
                             default=o.get(CONF_PV_MORNING_ENABLED, DEFAULT_PV_MORNING_ENABLED)): bool,
                vol.Optional(CONF_PV_MORNING_TIME,
                             default=o.get(CONF_PV_MORNING_TIME, DEFAULT_PV_MORNING_TIME)): _TIME,
                vol.Optional(CONF_PV_COLDSTART,
                             default=o.get(CONF_PV_COLDSTART, DEFAULT_PV_COLDSTART)): _WATT,
                vol.Optional(CONF_PV_COLDSTART_DELTA,
                             default=o.get(CONF_PV_COLDSTART_DELTA, DEFAULT_PV_COLDSTART_DELTA)): _KELVIN,
                vol.Optional(CONF_PV_MIN_RUN,
                             default=o.get(CONF_PV_MIN_RUN, DEFAULT_PV_MIN_RUN)): _MINUTES,
                vol.Optional(CONF_PV_MAX_STARTS,
                             default=o.get(CONF_PV_MAX_STARTS, DEFAULT_PV_MAX_STARTS)): _STARTS,
                vol.Optional(CONF_PV_DEBOUNCE, default=o.get(CONF_PV_DEBOUNCE, DEFAULT_PV_DEBOUNCE)): int,
                vol.Optional(CONF_PV_MIN_OFF, default=o.get(CONF_PV_MIN_OFF, DEFAULT_PV_MIN_OFF)): int,
                vol.Optional(CONF_PV_ESCALATION,
                             default=o.get(CONF_PV_ESCALATION, DEFAULT_PV_ESCALATION)): _ESCALATION,
                vol.Optional(CONF_PV_BOOST_ONLY_NEGATIVE_PRICE,
                             default=o.get(CONF_PV_BOOST_ONLY_NEGATIVE_PRICE,
                                           DEFAULT_PV_BOOST_ONLY_NEGATIVE_PRICE)): bool,
                vol.Optional(CONF_PV_NEGATIVE_PRICE_SENSOR): _NEGATIVE_PRICE_SENSOR,
            }
        )
    return vol.Schema(fields)


def _temp_order_error(merged: dict[str, Any]) -> str | None:
    """Plausibilität der PV-Zieltemperaturen: Normal < Erhöht ≤ Boost.

    Ohne echte Staffelung kollabieren die Regelstufen: Ist Erhöht nicht höher als
    Normal, gibt es keine Zwischenstufe mehr, und die Solar-Boost-Stufe (Verdichter
    allein) kann nicht mehr von der Normalstufe unterschieden werden. ``pv.py`` klemmt
    verdrehte Werte zwar zur Laufzeit ab, aber ein Hinweis beim Speichern ist ehrlicher
    als eine stillschweigende Korrektur.
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
        critical = float(merged.get(CONF_EMERGENCY_CRITICAL, DEFAULT_EMERGENCY_CRITICAL))
    except (TypeError, ValueError):
        return None
    if pv_high < heater_power + 50:
        return "pv_high_too_low"
    return None


async def _test_connection(host: str, port: int, slave: int) -> bool:
    """Kurzer Verbindungstest zum Modbus-Konverter (ein Register lesen)."""
    client = AsyncModbusTcpClient(host, port=port)
    try:
        await client.connect()
        if not client.connected:
            return False
        try:
            rr = await client.read_holding_registers(READ_START, count=1, device_id=slave)
        except TypeError:
            rr = await client.read_holding_registers(READ_START, count=1, slave=slave)
        return not rr.isError()
    except Exception:  # noqa: BLE001
        return False
    finally:
        client.close()


class HaierModbusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Einrichtungsassistent: Verbindung -> COP -> PV."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._cop: dict[str, Any] = {}
        self._pv: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input.get(CONF_PORT, DEFAULT_PORT)}"
            )
            self._abort_if_unique_id_configured()
            ok = await _test_connection(
                user_input[CONF_HOST],
                user_input.get(CONF_PORT, DEFAULT_PORT),
                user_input.get(CONF_SLAVE, DEFAULT_SLAVE),
            )
            if not ok:
                errors["base"] = "cannot_connect"
            else:
                self._data = user_input
                return await self.async_step_cop()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_SLAVE, default=DEFAULT_SLAVE): int,
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
                vol.Required(CONF_MODEL, default=DEFAULT_MODEL_KEY): _MODEL,
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_cop(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            self._cop = {k: v for k, v in user_input.items() if v not in ("", None)}
            return await self.async_step_pv()
        return self.async_show_form(step_id="cop", data_schema=_cop_schema({}))

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
            details = {k: v for k, v in user_input.items() if v not in ("", None)}
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
            schema = self.add_suggested_values_to_schema(schema, user_input)
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
    """Optionen in zwei Schritten: ``init`` (Verbindung/COP/Notfall + PV-Modus),
    danach ``pv`` (genau die Felder des gewählten PV-Modus). Bei PV-Modus „Aus“
    wird der PV-Schritt übersprungen.
    """

    _pending: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            self._pending = {k: v for k, v in user_input.items() if v not in ("", None)}
            if self._pending.get(CONF_PV_MODE, DEFAULT_PV_MODE) == PV_MODE_OFF:
                return self.async_create_entry(title="", data=self._pending)
            return await self.async_step_pv()

        o = self.config_entry.options
        d = self.config_entry.data

        def cur(key: str, default: Any) -> Any:
            return o.get(key, d.get(key, default))

        connection = {
            vol.Optional(CONF_HOST, default=cur(CONF_HOST, "")): str,
            vol.Optional(CONF_PORT, default=cur(CONF_PORT, DEFAULT_PORT)): int,
            vol.Optional(CONF_SLAVE, default=cur(CONF_SLAVE, DEFAULT_SLAVE)): int,
            vol.Optional(CONF_MODEL, default=cur(CONF_MODEL, DEFAULT_MODEL_KEY)): _MODEL,
            vol.Optional(CONF_SCAN_INTERVAL, default=cur(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): int,
            vol.Optional(CONF_AMBIENT_OFFSET, default=cur(CONF_AMBIENT_OFFSET, DEFAULT_AMBIENT_OFFSET)): _OFFSET,
        }

        emergency = {
            vol.Optional(CONF_EMERGENCY_ENABLED, default=cur(CONF_EMERGENCY_ENABLED, False)): bool,
            vol.Optional(CONF_EMERGENCY_CRITICAL,
                         default=cur(CONF_EMERGENCY_CRITICAL, DEFAULT_EMERGENCY_CRITICAL)): _TEMP,
            vol.Optional(CONF_EMERGENCY_RECOVER,
                         default=cur(CONF_EMERGENCY_RECOVER, DEFAULT_EMERGENCY_RECOVER)): _TEMP,
            vol.Optional(CONF_EMERGENCY_MODE,
                         default=cur(CONF_EMERGENCY_MODE, DEFAULT_EMERGENCY_MODE)): _EMERGENCY_MODE,
        }

        legionella = {
            vol.Optional(CONF_LEGIONELLA_ENABLED,
                         default=cur(CONF_LEGIONELLA_ENABLED, False)): bool,
            vol.Optional(CONF_LEGIONELLA_TARGET,
                         default=cur(CONF_LEGIONELLA_TARGET, DEFAULT_LEGIONELLA_TARGET)): _TEMP,
            vol.Optional(CONF_LEGIONELLA_INTERVAL,
                         default=cur(CONF_LEGIONELLA_INTERVAL, DEFAULT_LEGIONELLA_INTERVAL)): _DAYS,
            vol.Optional(CONF_LEGIONELLA_BOTTOM,
                         default=cur(CONF_LEGIONELLA_BOTTOM, DEFAULT_LEGIONELLA_BOTTOM)): _TEMP,
            vol.Optional(CONF_LEGIONELLA_HOLD,
                         default=cur(CONF_LEGIONELLA_HOLD, DEFAULT_LEGIONELLA_HOLD)): _MINUTES,
            vol.Optional(CONF_LEGIONELLA_WINDOW_START,
                         default=cur(CONF_LEGIONELLA_WINDOW_START, DEFAULT_LEGIONELLA_WINDOW_START)): _TIME,
            vol.Optional(CONF_LEGIONELLA_WINDOW_END,
                         default=cur(CONF_LEGIONELLA_WINDOW_END, DEFAULT_LEGIONELLA_WINDOW_END)): _TIME,
        }

        schema = vol.Schema(connection)
        schema = schema.extend(_cop_schema(o).schema)
        schema = schema.extend(_pv_mode_schema(o).schema)
        schema = schema.extend(emergency)
        schema = schema.extend(legionella)
        schema = self.add_suggested_values_to_schema(schema, o)
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_pv(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Zweiter Schritt: modus-spezifische PV-Felder. Speichert die gesamten
        Optionen (Seite 1 + Seite 2)."""
        errors: dict[str, str] = {}
        mode = self._pending.get(CONF_PV_MODE, DEFAULT_PV_MODE)
        if user_input is not None:
            details = {k: v for k, v in user_input.items() if v not in ("", None)}
            merged = {**self._pending, **details}
            if mode == PV_MODE_COORDINATOR and not merged.get(CONF_PV_SENSOR):
                errors["base"] = "pv_sensor_required"
            elif (order_error := _temp_order_error(merged)) is not None:
                errors["base"] = order_error
            elif mode == PV_MODE_COORDINATOR and (coord_error := _pv_coordinator_error(merged)) is not None:
                errors["base"] = coord_error
            else:
                return self.async_create_entry(title="", data=merged)

        base = {**self.config_entry.options, **self._pending, **(user_input or {})}
        schema = _pv_detail_schema(base, mode)
        schema = self.add_suggested_values_to_schema(schema, base)
        return self.async_show_form(step_id="pv", data_schema=schema, errors=errors)
