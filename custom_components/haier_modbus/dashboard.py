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

from .const import (
    DASHBOARD_ICON,
    DASHBOARD_LEGACY_URL_PATH,
    DASHBOARD_TITLE,
    DASHBOARD_URL_PATH,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_DASH_DIR = "haier_bwwp"
_DASH_FILE = "dashboard.yaml"


def _build_config(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Dashboard-Config mit real aufgelösten entity_ids bauen."""
    reg = er.async_get(hass)

    def eid(domain: str, key: str) -> str | None:
        ent_id = reg.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
        if not ent_id:
            return None
        ent = reg.async_get(ent_id)
        if ent is not None and ent.disabled_by is not None:
            return None  # deaktivierte Entitäten (z. B. Solar/Kessel) nicht aufnehmen
        return ent_id

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

    def section(title: str | None, cards: list, span: int = 1) -> dict | None:
        cards = [c for c in cards if c]
        if not cards:
            return None
        sec: dict = {"type": "grid", "cards": cards}
        if title:
            sec["title"] = title
        if span > 1:
            sec["column_span"] = span
        return sec

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
            tile("select", "mode", "Modus", features=[{"type": "select-options"}]),
            tile("switch", "active", "Betrieb", features=[{"type": "toggle"}]),
            tile("switch", "boost", "Boost", features=[{"type": "toggle"}]),
            tile("switch", "mute", "Leise", features=[{"type": "toggle"}]),
            tile("switch", "sterilize", "Sterilisation", features=[{"type": "toggle"}]),
        ]),
        {
            "type": "button",
            "name": "Einstellungen",
            "icon": "mdi:cog",
            "tap_action": {
                "action": "navigate",
                "navigation_path": f"/config/integrations/integration/{DOMAIN}",
            },
        },
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
            tile("sensor", "link_status", "Modbus-Status"),
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

    def statgraph(title: str, period: str, specs: list) -> dict | None:
        ents = [e for e in (eid(d, k) for d, k in specs) if e]
        if not ents:
            return None
        return {
            "type": "statistics-graph",
            "title": title,
            "period": period,
            "stat_types": ["change"],
            "chart_type": "bar",
            "entities": ents,
        }

    _avg_h = {"type": "line", "group_by": {"func": "avg", "duration": "1h"}}
    chart_month = statgraph("Energie pro Monat", "month",
                            [("sensor", "total_heat"), ("sensor", "total_elec")])
    chart_temp = apex(
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
        all_series_config={"stroke_width": 2},
    )
    chart_cop = apex(
        "COP seit Bezugsdatum (30 Tage)", "30d",
        [("sensor", "cop_reference", "COP",
          {"type": "line", "curve": "smooth", "group_by": {"func": "avg", "duration": "1d"}})],
        yaxis=[{"min": 0, "decimals": 2}],
    )

    # Bedien-/Status-Kacheln oben (je eine Spalte); die Diagramme darunter in
    # EINER vollbreiten Sektion als horizontale Reihe -> nebeneinander, gleich
    # breit, ohne Masonry-Lücken. Nur als editierbarer Startpunkt gedacht; der
    # Nutzer kann im UI frei umsortieren.
    chart_cards = [c for c in (chart_month, chart_temp, chart_cop) if c]
    charts_row = {"type": "horizontal-stack", "cards": chart_cards} if chart_cards else None
    sections = [
        steuerung,
        temps,
        status,
        energie,
        section("Verläufe", [charts_row], span=3) if charts_row else None,
    ]
    sections = [s for s in sections if s]
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


def _remove_legacy_yaml_dashboard(hass: HomeAssistant) -> None:
    """Altes, gesperrtes YAML-Dashboard (``haier-bwwp``) aus der Seitenleiste nehmen.

    Bestehende Installationen hatten ein nicht editierbares YAML-Dashboard; das
    wird hier entfernt, damit nicht zwei Einträge nebeneinander stehen. Die
    YAML-Datei bleibt liegen (schadet nicht), wird aber nicht mehr registriert.
    """
    try:
        frontend.async_remove_panel(hass, DASHBOARD_LEGACY_URL_PATH)
    except Exception:  # noqa: BLE001
        pass
    lovelace = hass.data.get("lovelace")
    dashboards = getattr(lovelace, "dashboards", None)
    if isinstance(dashboards, dict):
        dashboards.pop(DASHBOARD_LEGACY_URL_PATH, None)


async def _seed_storage_dashboard(hass: HomeAssistant, config: dict) -> bool:
    """Editierbares Storage-Dashboard EINMALIG anlegen.

    Gibt True zurück, wenn ein Storage-Dashboard existiert (neu angelegt ODER
    bereits vorhanden – dann bleiben die Anpassungen des Nutzers unangetastet).
    Greift auf die interne Lovelace-Collection zu; bei abweichender API wird
    False geliefert, sodass der Aufrufer auf YAML zurückfallen kann.
    """
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return False
    dashboards = getattr(lovelace, "dashboards", None)
    collection = getattr(lovelace, "dashboards_collection", None)
    if not isinstance(dashboards, dict) or collection is None:
        return False

    # Bereits vorhanden? -> nicht überschreiben (Nutzer-Layout behalten).
    if DASHBOARD_URL_PATH in dashboards:
        return True
    try:
        items = list(collection.async_items())
    except Exception:  # noqa: BLE001
        items = []
    if any((i or {}).get("url_path") == DASHBOARD_URL_PATH for i in items):
        return True

    # Registry-Eintrag anlegen (registriert via Listener Panel + LovelaceStorage).
    await collection.async_create_item(
        {
            "url_path": DASHBOARD_URL_PATH,
            "title": DASHBOARD_TITLE,
            "icon": DASHBOARD_ICON,
            "show_in_sidebar": True,
            "require_admin": False,
        }
    )
    store = dashboards.get(DASHBOARD_URL_PATH)
    if store is None:
        return False
    await store.async_save(config)  # Start-Layout hinterlegen
    return True


async def _register_yaml_dashboard(hass: HomeAssistant, config: dict) -> None:
    """Fallback: Dashboard als (nicht editierbares) Lovelace-YAML + Panel anmelden."""
    import yaml

    text = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    path = Path(hass.config.path(_DASH_DIR)) / _DASH_FILE
    await hass.async_add_executor_job(_write, path, text)

    lovelace = hass.data.get("lovelace")
    dashboards = getattr(lovelace, "dashboards", None)
    if isinstance(dashboards, dict) and DASHBOARD_URL_PATH not in dashboards:
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


async def async_register_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Editierbares Dashboard bereitstellen (Storage; YAML nur als Fallback)."""
    try:
        _remove_legacy_yaml_dashboard(hass)
        config = _build_config(hass, entry)
        if await _seed_storage_dashboard(hass, config):
            _LOGGER.info(
                "Editierbares Haier-Dashboard unter /%s", DASHBOARD_URL_PATH
            )
            return
        await _register_yaml_dashboard(hass, config)
        _LOGGER.info(
            "Haier-Dashboard (YAML-Fallback) unter /%s", DASHBOARD_URL_PATH
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Dashboard-Registrierung übersprungen: %s", exc)


async def async_remove_dashboard(hass: HomeAssistant) -> None:
    """Beim Entladen NICHTS löschen.

    Das Storage-Dashboard gehört nun dem Nutzer (Drag&Drop-Anpassungen) und
    bleibt über Reloads/Neustarts erhalten. Ein evtl. YAML-Fallback-Panel wird
    beim nächsten Setup ohnehin mit ``update=True`` neu registriert.
    """
    return
