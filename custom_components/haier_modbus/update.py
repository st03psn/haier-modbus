"""Update-Entität für das mitgelieferte Dashboard-Layout.

Meldet ein Update, wenn das Haier-Dashboard eine ältere Layout-Generation hat und
nicht automatisch aktualisiert werden durfte (vom Nutzer angepasst bzw. aus einer
Version vor v2.0.0). Bleibt unter *Einstellungen* sichtbar, bis es installiert ist
– auch wenn der Reparatur-Hinweis mit „Nein“ beantwortet wurde. *Installieren*
übernimmt das automatisch angelegte Vergleichs-Dashboard (samt Nutzer-Änderungen);
gibt es keines, wird das Dashboard neu aufgebaut (wie Dienst ``rebuild_dashboard``).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, localized_title
from .dashboard import (
    LAYOUT_SIGNAL,
    LAYOUT_STATUS_KEY,
    async_promote_compare_dashboard,
    async_rebuild_dashboard,
)
from .entity import HaierModbusEntity

_RELEASE_URL = "https://github.com/st03psn/haier-modbus#dashboard"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HaierDashboardUpdate(coordinator)])


class HaierDashboardUpdate(HaierModbusEntity, UpdateEntity):
    _attr_translation_key = "dashboard"
    _attr_supported_features = UpdateEntityFeature.INSTALL
    _attr_release_url = _RELEASE_URL
    _attr_icon = "mdi:view-dashboard-edit-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_dashboard"

    @property
    def available(self) -> bool:
        # Unabhängig vom Modbus-Zustand – betrifft nur das Dashboard.
        return True

    def _status(self) -> dict:
        return self.hass.data.get(LAYOUT_STATUS_KEY) or {}

    @property
    def latest_version(self) -> str | None:
        latest = self._status().get("latest")
        return str(latest) if latest else None

    @property
    def installed_version(self) -> str | None:
        st = self._status()
        applied = st.get("applied")
        if applied is None:  # Dashboard abgeschaltet / unbekannt -> kein Update melden
            return self.latest_version
        return str(applied)

    @property
    def title(self) -> str:
        de = (self.hass.config.language or "en").lower().startswith("de")
        return "Haier-Dashboard (Layout)" if de else "Haier dashboard (layout)"

    @property
    def release_summary(self) -> str:
        de = (self.hass.config.language or "en").lower().startswith("de")
        # HA kürzt release_summary auf 255 Zeichen.
        title = localized_title(self.hass.config.language)
        if self._status().get("compare"):
            return (
                f"Das neue Layout liegt als „{title} (neu)“ in der Seitenleiste zum "
                "Vergleich bereit. Aktualisieren übernimmt es samt deiner Änderungen daran "
                "als Haier-Dashboard und ersetzt das bisherige."
                if de else
                f"The new layout is in the sidebar as “{title} (new)” for comparison. "
                "Updating adopts it, including your changes to it, as the Haier dashboard "
                "and replaces the previous one."
            )
        return (
            "Aktualisieren ersetzt das Haier-Dashboard durch das neue Layout (eigene "
            "Anpassungen gehen verloren). Erst vergleichen: Integration Haier → Zahnrad → "
            "Dashboard → „Neues Dashboard zum Vergleich anlegen“."
            if de else
            "Updating replaces the Haier dashboard with the new layout (your own changes "
            "are lost). To compare first: Haier integration → gear icon → Dashboard → "
            "“Create new dashboard for comparison”."
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, LAYOUT_SIGNAL, self._handle_layout)
        )

    @callback
    def _handle_layout(self) -> None:
        self.async_write_ha_state()

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        if self._status().get("compare"):
            await async_promote_compare_dashboard(self.hass, self.coordinator.entry)
        else:
            await async_rebuild_dashboard(self.hass, self.coordinator.entry)
