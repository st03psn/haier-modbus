"""Mitgeliefertes Dashboard – beim Setup dynamisch erzeugt und registriert.

Die Entitäts-IDs werden über die Registry aus den ``unique_id``s aufgelöst
(``<entry>_<key>``), nicht hartkodiert. Dadurch passt das Dashboard auf jede
Installation – auch bei abweichenden/„umbenannten" entity_ids – ohne dass IDs
geändert werden müssen. Karten zu (noch) fehlenden Entitäten werden ausgelassen.

Registrierung wie üblich für mitgelieferte Dashboards: generiertes YAML unter
``<config>/haier_bwwp/dashboard.yaml`` ablegen, als Lovelace-YAML-Dashboard +
Seitenleisten-Panel anmelden. Alles gekapselt – Fehler bleiben folgenlos.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DASHBOARD_ICON, DASHBOARD_TITLE, DASHBOARD_URL_PATH, DOMAIN

_LOGGER = logging.getLogger(__name__)

_DASH_DIR = "haier_bwwp"
_DASH_FILE = "dashboard.yaml"


def _build_config(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Dashboard-Config mit real aufgelösten entity_ids bauen."""
    reg = er.async_get(hass)

    def eid(domain: str, key: str) -> str | None:
        return reg.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")

    def tile(domain: str, key: str, name: str, **extra) -> dict | None:
        entity = eid(domain, key)
        if not entity:
            return None
        card = {"type": "tile", "entity": entity, "name": name}
        card.update(extra)
        return card

    def grid(cards: list, columns: int = 2) -> dict | None:
        cards = [c for c in cards if c]
        return {"type": "grid", "columns": columns, "square": False, "cards": cards} if cards else None

    def section(title: str, cards: list) -> dict | None:
        cards = [c for c in cards if c]
        return {"title": title, "cards": cards} if cards else None

    def apex(title: str, span: str, series_spec: list, **extra) -> dict | None:
        series = []
        for dom, key, name, opts in series_spec:
            entity = eid(dom, key)
            if entity:
                series.append({"entity": entity, "name": name, **opts})
        if not series:
            return None
        card = {
            "type": "custom:apexcharts-card",
            "header": {"show": True, "title": title},
            "graph_span": span,
            "series": series,
        }
        card.update(extra)
        return card

    steuerung = section("Steuerung", [
        tile("water_heater", "water_heater", "Brauchwasser",
             features=[{"type": "target-temperature"}]),
        grid([
            tile("number", "set_temp", "Solltemperatur",
                 features=[{"type": "numeric-input", "style": "slider"}]),
            tile("select", "mode", "Modus"),
            tile("switch", "active", "Aktiv", features=[{"type": "toggle"}]),
            tile("switch", "boost", "Boost", features=[{"type": "toggle"}]),
            tile("switch", "mute", "Leise", features=[{"type": "toggle"}]),
            tile("switch", "sterilize", "Sterilisation", features=[{"type": "toggle"}]),
        ]),
    ])

    temps = section("Temperaturen", [grid([
        tile("sensor", "water_temp", "Wasser"),
        tile("sensor", "target_temp", "Ziel"),
        tile("sensor", "tank_top", "Tank oben"),
        tile("sensor", "tank_bottom", "Tank unten"),
        tile("sensor", "ambient", "Umgebung"),
        tile("sensor", "hotwater_pct", "Warmwasser"),
    ])])

    status = section("Status", [
        tile("sensor", "current_source", "Aktuelle Quelle"),
        grid([
            tile("binary_sensor", "status_wp", "Wärmepumpe", color="green"),
            tile("binary_sensor", "status_heater", "Heizstab", color="orange"),
            tile("binary_sensor", "status_solar", "Solar", color="amber"),
            tile("binary_sensor", "status_boiler", "Kessel", color="red"),
            tile("binary_sensor", "connection", "Verbindung"),
            tile("sensor", "fault", "Fehlercode"),
        ]),
    ])

    energie = section("Energie & COP", [grid([
        tile("sensor", "cop_reference", "COP (seit Start)", color="green"),
        tile("sensor", "cop_month", "COP (Monat)"),
        tile("sensor", "cop_year", "JAZ (Jahr)"),
        tile("sensor", "cop_prev_year", "JAZ (Vorjahr)"),
        tile("sensor", "heat_total", "Wärme gesamt"),
        tile("sensor", "total_elec", "Strom gesamt"),
        tile("sensor", "heat_year", "Wärme (Gerät)"),
        tile("sensor", "hp_elec_year", "WP-Strom (Jahr)"),
        tile("sensor", "heater_elec_year", "Heizstab (Jahr)"),
    ])])

    _avg_h = {"type": "line", "group_by": {"func": "avg", "duration": "1h"}}
    verlauf = section("Verlauf", [
        apex(
            "Temperaturen (7 Tage)", "7d",
            [
                ("sensor", "water_temp", "Wasser", _avg_h),
                ("sensor", "tank_top", "Tank oben", _avg_h),
                ("sensor", "tank_bottom", "Tank unten", _avg_h),
                ("sensor", "ambient", "Umgebung", _avg_h),
                ("number", "set_temp", "Soll",
                 {"type": "line", "curve": "stepline", "group_by": {"func": "max", "duration": "1h"}}),
            ],
            yaxis=[{"min": 35, "max": 60, "decimals": 0}],
            stroke_width=2,
        ),
        apex(
            "COP seit Bezugsdatum (30 Tage)", "30d",
            [("sensor", "cop_reference", "COP",
              {"type": "line", "curve": "smooth", "group_by": {"func": "avg", "duration": "1d"}})],
            yaxis=[{"min": 0, "decimals": 2}],
        ),
    ])

    sections = [s for s in (steuerung, temps, status, energie, verlauf) if s]
    return {
        "views": [{
            "title": "Übersicht",
            "path": "home",
            "type": "sections",
            "max_columns": 3,
            "sections": sections,
        }]
    }


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


async def async_register_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Dashboard erzeugen, ablegen und als Lovelace-YAML + Panel registrieren."""
    try:
        import yaml

        config = _build_config(hass, entry)
        text = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
        path = Path(hass.config.path(_DASH_DIR)) / _DASH_FILE
        await hass.async_add_executor_job(_write, path, text)

        lovelace = hass.data.get("lovelace")
        dashboards = getattr(lovelace, "dashboards", None)
        if dashboards is not None and DASHBOARD_URL_PATH not in dashboards:
            from homeassistant.components.lovelace.dashboard import LovelaceYAML

            dashboards[DASHBOARD_URL_PATH] = LovelaceYAML(
                hass,
                DASHBOARD_URL_PATH,
                {
                    "mode": "yaml",
                    "filename": str(path),
                    "title": DASHBOARD_TITLE,
                    "icon": DASHBOARD_ICON,
                    "show_in_sidebar": True,
                    "require_admin": False,
                },
            )

        frontend.async_register_built_in_panel(
            hass,
            component_name="lovelace",
            sidebar_title=DASHBOARD_TITLE,
            sidebar_icon=DASHBOARD_ICON,
            frontend_url_path=DASHBOARD_URL_PATH,
            config={"mode": "yaml", "filename": str(path)},
            require_admin=False,
            update=True,
        )
        _LOGGER.info("Haier-BWWP-Dashboard registriert unter /%s", DASHBOARD_URL_PATH)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Dashboard-Registrierung übersprungen: %s", exc)


async def async_remove_dashboard(hass: HomeAssistant) -> None:
    """Panel + Lovelace-Eintrag entfernen (Datei bleibt, schadet nicht)."""
    try:
        frontend.async_remove_panel(hass, DASHBOARD_URL_PATH)
    except Exception:  # noqa: BLE001
        pass
    lovelace = hass.data.get("lovelace")
    dashboards = getattr(lovelace, "dashboards", None)
    if isinstance(dashboards, dict):
        dashboards.pop(DASHBOARD_URL_PATH, None)
