"""Config- und Options-Flow – alles über die HA-Oberfläche konfigurierbar."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_COP_ELEC_ENTITY,
    CONF_COP_ELEC_SOURCE,
    CONF_COP_ENABLED,
    CONF_COP_HEAT_ENTITY,
    CONF_COP_HEAT_SOURCE,
    CONF_ENERGY_SCALE,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    DEFAULT_ENERGY_SCALE,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DOMAIN,
    SOURCE_EXTERNAL,
    SOURCE_MODBUS,
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


class HaierModbusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Einrichtung: Verbindungsdaten."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input.get(CONF_PORT, DEFAULT_PORT)}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Haier Brauchwasserwärmepumpe", data=user_input
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_SLAVE, default=DEFAULT_SLAVE): int,
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

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
            # Leere Entity-Auswahl als nicht gesetzt behandeln.
            cleaned = {k: v for k, v in user_input.items() if v not in ("", None)}
            return self.async_create_entry(title="", data=cleaned)

        o = self.config_entry.options

        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=o.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): int,
                vol.Optional(CONF_COP_ENABLED, default=o.get(CONF_COP_ENABLED, True)): bool,
                vol.Optional(CONF_COP_ELEC_SOURCE, default=o.get(CONF_COP_ELEC_SOURCE, SOURCE_MODBUS)): _SOURCE,
                vol.Optional(CONF_COP_ELEC_ENTITY): _ENERGY_ENTITY,
                vol.Optional(CONF_COP_HEAT_SOURCE, default=o.get(CONF_COP_HEAT_SOURCE, SOURCE_MODBUS)): _SOURCE,
                vol.Optional(CONF_COP_HEAT_ENTITY): _ENERGY_ENTITY,
                vol.Optional(CONF_ENERGY_SCALE, default=o.get(CONF_ENERGY_SCALE, DEFAULT_ENERGY_SCALE)): _SCALE,
            }
        )
        # Vorbelegung der Entity-Selektoren mit gespeicherten Werten.
        schema = self.add_suggested_values_to_schema(schema, o)
        return self.async_show_form(step_id="init", data_schema=schema)
