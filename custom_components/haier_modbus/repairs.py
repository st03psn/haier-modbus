"""Reparatur-Abläufe der Integration.

``dashboard_layout_update``: Für das Haier-Dashboard gibt es ein neues Layout, das
nicht automatisch eingespielt werden durfte (angepasst bzw. aus einer Version vor
2.0.0). Der Nutzer entscheidet mit Ja/Nein:

- **Ja:** neues Layout übernehmen. Gibt es ein Vergleichs-Dashboard, wird dieses
  (samt Änderungen) übernommen, sonst das Haier-Dashboard neu aufgebaut.
- **Nein:** Dashboard bleibt; für diese Layout-Generation wird nicht mehr gefragt.

Schließen ohne Auswahl lässt den Hinweis stehen.
"""

from __future__ import annotations

import logging

from homeassistant import data_entry_flow
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant

from .dashboard import (
    DASHBOARD_ISSUE_ID,
    LAYOUT_STATUS_KEY,
    async_decline_layout,
    async_promote_compare_dashboard,
    async_rebuild_dashboard,
)

_LOGGER = logging.getLogger(__name__)


class DashboardLayoutRepairFlow(RepairsFlow):
    """Ja/Nein zum neuen Dashboard-Layout."""

    def __init__(self, entry_id: str | None) -> None:
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        return self.async_show_menu(step_id="init", menu_options=["adopt", "keep"])

    async def async_step_adopt(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        entry = self.hass.config_entries.async_get_entry(self._entry_id or "")
        if entry is None:
            return self.async_abort(reason="entry_missing")
        try:
            if (self.hass.data.get(LAYOUT_STATUS_KEY) or {}).get("compare"):
                await async_promote_compare_dashboard(self.hass, entry)
            else:
                await async_rebuild_dashboard(self.hass, entry)
        except Exception:  # noqa: BLE001 – Grund steht im Log
            _LOGGER.exception("Dashboard-Layout übernehmen fehlgeschlagen")
            return self.async_abort(reason="adopt_failed")
        return self.async_create_entry(data={})

    async def async_step_keep(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        await async_decline_layout(self.hass)
        return self.async_create_entry(data={})


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    if issue_id == DASHBOARD_ISSUE_ID:
        entry_id = (data or {}).get("entry_id")
        return DashboardLayoutRepairFlow(str(entry_id) if entry_id else None)
    return ConfirmRepairFlow()
