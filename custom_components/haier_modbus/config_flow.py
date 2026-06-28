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
    CONF_EMERGENCY_RECOVER,
    CONF_ENERGY_SCALE,
    CONF_HOST,
    CONF_MODEL,
    CONF_PORT,
    CONF_PV_DEBOUNCE,
    CONF_PV_ESCALATION,
    CONF_PV_HIGH,
    CONF_PV_HOLD,
    CONF_PV_MIN_OFF,
    CONF_PV_MODE,
    CONF_PV_MORNING_ENABLED,
    CONF_PV_MORNING_TIME,
    CONF_PV_RERAISE_ENABLED,
    CONF_PV_RERAISE_THRESHOLD,
    CONF_PV_SENSOR,
    CONF_PV_TEMP_BASE,
    CONF_PV_TEMP_HIGH,
    CONF_PV_TEMP_NORMAL,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    DEFAULT_AMBIENT_OFFSET,
    DEFAULT_EMERGENCY_CRITICAL,
    DEFAULT_EMERGENCY_RECOVER,
    DEFAULT_ENERGY_SCALE,
    DEFAULT_MODEL_KEY,
    DEFAULT_PORT,
    DEFAULT_PV_DEBOUNCE,
    DEFAULT_PV_ESCALATION,
    DEFAULT_PV_HIGH,
    DEFAULT_PV_HOLD,
    DEFAULT_PV_MIN_OFF,
    DEFAULT_PV_MODE,
    DEFAULT_PV_MORNING_ENABLED,
    DEFAULT_PV_MORNING_TIME,
    DEFAULT_PV_RERAISE_ENABLED,
    DEFAULT_PV_RERAISE_THRESHOLD,
    DEFAULT_PV_TEMP_BASE,
    DEFAULT_PV_TEMP_HIGH,
    DEFAULT_PV_TEMP_NORMAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DOMAIN,
    MODELS,
    PV_ESC_BOOST,
    PV_ESC_ELEC,
    PV_ESC_NONE,
    PV_MODE_COORDINATOR,
    PV_MODE_EXECUTOR,
    PV_MODE_OFF,
    READ_START,
    SET_TEMP_MAX,
    SET_TEMP_MIN,
    localized_title,
)

_ENERGY_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
)
_PV_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power")
)
_ESCALATION = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[PV_ESC_NONE, PV_ESC_BOOST, PV_ESC_ELEC],
        translation_key="pv_escalation",
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
_OFFSET = selector.NumberSelector(
    selector.NumberSelectorConfig(min=-15, max=15, step=0.1,
                                  unit_of_measurement="°C", mode=selector.NumberSelectorMode.BOX)
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


def _pv_schema(o: dict[str, Any]) -> vol.Schema:
    """PV-Betriebsmodus + Felder – im Wizard und im Options-Flow identisch.

    Oberster Schalter ist der **PV-Modus** (Aus/Coordinator/Executor). HA-Formulare
    können Felder nicht live abhängig vom Dropdown ein-/ausblenden – daher richten
    sich die zusätzlichen Felder nach dem *gespeicherten* Modus (nach dem Übernehmen
    erscheinen sie beim erneuten Öffnen):
      - **Coordinator:** PV-Sensor, Zieltemps und alle Regel-Schwellen.
      - **Executor:** nur die Zieltemps (Mechanik fürs Programm-Select); geregelt
        wird über ``select.haier_hwhp_pv_program`` durch das HEMS.
    """
    fields: dict[Any, Any] = {
        vol.Optional(CONF_PV_MODE, default=o.get(CONF_PV_MODE, DEFAULT_PV_MODE)): _PV_MODE,
        # Immer sichtbar, damit der Sensor im selben Schritt gesetzt werden kann,
        # in dem auf Coordinator umgestellt wird (sonst Validierungs-Sackgasse).
        vol.Optional(CONF_PV_SENSOR): _PV_SENSOR,
    }
    mode = o.get(CONF_PV_MODE, DEFAULT_PV_MODE)

    if mode in (PV_MODE_COORDINATOR, PV_MODE_EXECUTOR):
        # Zieltemps sind die gemeinsame Mechanik beider Modi.
        fields.update(
            {
                vol.Optional(CONF_PV_TEMP_HIGH, default=o.get(CONF_PV_TEMP_HIGH, DEFAULT_PV_TEMP_HIGH)): _TEMP,
                vol.Optional(CONF_PV_TEMP_NORMAL,
                             default=o.get(CONF_PV_TEMP_NORMAL, DEFAULT_PV_TEMP_NORMAL)): _TEMP,
                vol.Optional(CONF_PV_TEMP_BASE, default=o.get(CONF_PV_TEMP_BASE, DEFAULT_PV_TEMP_BASE)): _TEMP,
            }
        )

    if mode == PV_MODE_COORDINATOR:
        fields.update(
            {
                vol.Optional(CONF_PV_HOLD, default=o.get(CONF_PV_HOLD, DEFAULT_PV_HOLD)): _WATT,
                vol.Optional(CONF_PV_RERAISE_THRESHOLD,
                             default=o.get(CONF_PV_RERAISE_THRESHOLD, DEFAULT_PV_RERAISE_THRESHOLD)): _WATT,
                vol.Optional(CONF_PV_RERAISE_ENABLED,
                             default=o.get(CONF_PV_RERAISE_ENABLED, DEFAULT_PV_RERAISE_ENABLED)): bool,
                vol.Optional(CONF_PV_HIGH, default=o.get(CONF_PV_HIGH, DEFAULT_PV_HIGH)): _WATT,
                vol.Optional(CONF_PV_MORNING_ENABLED,
                             default=o.get(CONF_PV_MORNING_ENABLED, DEFAULT_PV_MORNING_ENABLED)): bool,
                vol.Optional(CONF_PV_MORNING_TIME,
                             default=o.get(CONF_PV_MORNING_TIME, DEFAULT_PV_MORNING_TIME)): _TIME,
                vol.Optional(CONF_PV_DEBOUNCE, default=o.get(CONF_PV_DEBOUNCE, DEFAULT_PV_DEBOUNCE)): int,
                vol.Optional(CONF_PV_MIN_OFF, default=o.get(CONF_PV_MIN_OFF, DEFAULT_PV_MIN_OFF)): int,
                vol.Optional(CONF_PV_ESCALATION,
                             default=o.get(CONF_PV_ESCALATION, DEFAULT_PV_ESCALATION)): _ESCALATION,
            }
        )
    return vol.Schema(fields)


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
        if user_input is not None:
            pv = {k: v for k, v in user_input.items() if v not in ("", None)}
            options = {**self._cop, **pv}
            return self.async_create_entry(
                title=localized_title(self.hass.config.language),
                data=self._data,
                options=options,
            )
        return self.async_show_form(step_id="pv", data_schema=_pv_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "HaierModbusOptionsFlow":
        return HaierModbusOptionsFlow()


class HaierModbusOptionsFlow(config_entries.OptionsFlow):
    """Optionen: Verbindung (Host/Port/Slave/Modell), Intervall, COP, PV."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned = {k: v for k, v in user_input.items() if v not in ("", None)}
            if cleaned.get(CONF_PV_MODE) == PV_MODE_COORDINATOR and not cleaned.get(CONF_PV_SENSOR):
                errors["base"] = "pv_sensor_required"
            else:
                return self.async_create_entry(title="", data=cleaned)

        o = {**self.config_entry.options, **(user_input or {})}
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
        }

        schema = vol.Schema(connection)
        schema = schema.extend(_cop_schema(o).schema)
        schema = schema.extend(_pv_schema(o).schema)
        schema = schema.extend(emergency)
        schema = self.add_suggested_values_to_schema(schema, o)
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
