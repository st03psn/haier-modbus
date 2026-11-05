"""Buttons: neues Dashboard-Layout vergleichen bzw. übernehmen."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .dashboard import (
    LAYOUT_SIGNAL,
    LAYOUT_STATUS_KEY,
    async_create_compare_dashboard,
    async_promote_compare_dashboard,
)
from .entity import HaierModbusEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        HaierDashboardButton(coordinator, "dashboard_compare", "mdi:view-dashboard-variant-outline"),
        HaierDashboardButton(coordinator, "dashboard_promote", "mdi:check-decagram-outline"),
    ])


class HaierDashboardButton(HaierModbusEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, key: str, icon: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_icon = icon
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"

    @property
    def available(self) -> bool:
        # Übernehmen nur, wenn es ein Vergleichs-Dashboard gibt; unabhängig von Modbus.
        if self._key == "dashboard_promote":
            return bool((self.hass.data.get(LAYOUT_STATUS_KEY) or {}).get("compare"))
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, LAYOUT_SIGNAL, self._handle_layout)
        )

    @callback
    def _handle_layout(self) -> None:
        self.async_write_ha_state()

    async def async_press(self) -> None:
        if self._key == "dashboard_compare":
            await async_create_compare_dashboard(self.hass, self.coordinator.entry)
        else:
            await async_promote_compare_dashboard(self.hass, self.coordinator.entry)
