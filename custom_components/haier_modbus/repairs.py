"""Reparatur-Abläufe der Integration.

``dashboard_layout_update``: Für das Haier-Dashboard gibt es ein neues Layout, das
nicht automatisch eingespielt werden durfte (angepasst bzw. aus einer Version vor
2.0.0). Der Nutzer entscheidet mit Ja/Nein:

- **Ja:** Haier-Dashboard mit dem neuen Layout neu aufbauen.
- **Erst vergleichen:** neues Layout zusätzlich als „… (neu)“ anlegen; der Hinweis
  bleibt stehen (Abbruch statt Abschluss) und bietet danach **Vergleichs-Dashboard
  übernehmen** an (samt Änderungen daran).
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
    async_create_compare_dashboard,
    async_decline_layout,
    async_promote_compare_dashboard,
    async_rebuild_dashboard,
)

_LOGGER = logging.getLogger(__name__)


class DashboardLayoutRepairFlow(RepairsFlow):
    """Ja/Nein zum neuen Dashboard-Layout."""

    def __init__(self, entry_id: str | None) -> None:
        self._entry_id = entry_id

    def _has_compare(self) -> bool:
        return bool((self.hass.data.get(LAYOUT_STATUS_KEY) or {}).get("compare"))

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        if self._has_compare():
            return self.async_show_menu(step_id="compare_ready",
                                        menu_options=["adopt_compare", "adopt", "keep"])
        return self.async_show_menu(step_id="init", menu_options=["adopt", "compare", "keep"])

    async def _run(self, handler, *, finish: bool) -> data_entry_flow.FlowResult:
        entry = self.hass.config_entries.async_get_entry(self._entry_id or "")
        if entry is None:
            return self.async_abort(reason="entry_missing")
        try:
            await handler(self.hass, entry)
        except Exception:  # noqa: BLE001 – Grund steht im Log
            _LOGGER.exception("Dashboard-Aktion im Reparatur-Hinweis fehlgeschlagen")
            return self.async_abort(reason="adopt_failed")
        if finish:
            return self.async_create_entry(data={})
        # Abbruch statt Abschluss: der Hinweis bleibt für „übernehmen“ stehen.
        return self.async_abort(reason="compare_created")

    async def async_step_adopt(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        return await self._run(async_rebuild_dashboard, finish=True)

    async def async_step_adopt_compare(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        return await self._run(async_promote_compare_dashboard, finish=True)

    async def async_step_compare(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        return await self._run(async_create_compare_dashboard, finish=False)

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
