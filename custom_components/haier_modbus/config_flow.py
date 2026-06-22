"""Config- und Options-Flow – alles über die HA-Oberfläche konfigurierbar.

Einrichtung als Assistent in zwei Schritten:
  1. user  – Verbindung + Modell/Tank
  2. cop   – COP-/Energiequellen (direkt nach der Installation)

Dieselben COP-Felder sind später jederzeit über den Options-Flow änderbar.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from pymodbus.client import AsyncModbusTcpClient

from .const import (
    READ_START,
    CONF_COP_ELEC_ENTITY,
    CONF_COP_ELEC_SOURCE,
    CONF_COP_ENABLED,
    CONF_COP_HEAT_ENTITY,
    CONF_COP_HEAT_SOURCE,
    CONF_ENERGY_SCALE,
    CONF_HOST,
    CONF_MODEL,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    CONF_TANK_VOLUME,
    DEFAULT_ENERGY_SCALE,
    DEFAULT_MODEL_KEY,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DOMAIN,
    MODELS,
    SOURCE_EXTERNAL,
    SOURCE_MODBUS,
    TANK_VOLUME_L,
)

_ENERGY_ENTITY = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="energy")
)
_SOURCE = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[SOURCE_MODBUS, SOURCE_EXTERNAL],
        translation_key="energy_source",
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
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


def _cop_schema(o: dict[str, Any]) -> vol.Schema:
    """COP-/Energiequellen-Schema – im Wizard und im Options-Flow identisch."""
    return vol.Schema(
        {
            vol.Optional(CONF_COP_ENABLED, default=o.get(CONF_COP_ENABLED, True)): bool,
            vol.Optional(CONF_COP_ELEC_SOURCE, default=o.get(CONF_COP_ELEC_SOURCE, SOURCE_MODBUS)): _SOURCE,
            vol.Optional(CONF_COP_ELEC_ENTITY): _ENERGY_ENTITY,
            vol.Optional(CONF_COP_HEAT_SOURCE, default=o.get(CONF_COP_HEAT_SOURCE, SOURCE_MODBUS)): _SOURCE,
            vol.Optional(CONF_COP_HEAT_ENTITY): _ENERGY_ENTITY,
            vol.Optional(CONF_ENERGY_SCALE, default=o.get(CONF_ENERGY_SCALE, DEFAULT_ENERGY_SCALE)): _SCALE,
        }
    )


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
    """Einrichtungsassistent: Verbindung -> COP."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

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

        default_model = DEFAULT_MODEL_KEY
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_SLAVE, default=DEFAULT_SLAVE): int,
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
                vol.Required(CONF_MODEL, default=default_model): _MODEL,
                vol.Required(CONF_TANK_VOLUME, default=TANK_VOLUME_L): int,
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_cop(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            options = {k: v for k, v in user_input.items() if v not in ("", None)}
            return self.async_create_entry(
                title="Haier BWWP", data=self._data, options=options
            )
        return self.async_show_form(step_id="cop", data_schema=_cop_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "HaierModbusOptionsFlow":
        return HaierModbusOptionsFlow()


class HaierModbusOptionsFlow(config_entries.OptionsFlow):
    """Optionen: Abfrageintervall + COP-Energiequellen."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            cleaned = {k: v for k, v in user_input.items() if v not in ("", None)}
            return self.async_create_entry(title="", data=cleaned)

        o = self.config_entry.options

        schema = _cop_schema(o).extend(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=o.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): int,
            }
        )
        schema = self.add_suggested_values_to_schema(schema, o)
        return self.async_show_form(step_id="init", data_schema=schema)
