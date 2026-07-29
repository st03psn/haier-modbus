"""Mitgeliefertes Dashboard – beim Setup dynamisch erzeugt und registriert.

Die Entitäts-IDs werden über die Registry aus den ``unique_id``s aufgelöst
(``<entry>_<key>``), nicht hartkodiert. Dadurch passt das Dashboard auf jede
Installation – auch bei abweichenden/„umbenannten" entity_ids – ohne dass IDs
geändert werden müssen. Karten zu (noch) fehlenden Entitäten werden ausgelassen.

Registrierung wie üblich für mitgelieferte Dashboards: generiertes YAML im
Integrationsordner (``custom_components/haier_modbus/dashboard.yaml``) ablegen,
als Lovelace-YAML-Dashboard + Seitenleisten-Panel anmelden. Alles gekapselt –
Fehler bleiben folgenlos.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_PV_SENSOR,
    DASHBOARD_ICON,
    DASHBOARD_LEGACY_URL_PATH,
    DASHBOARD_URL_PATH,
    DOMAIN,
    localized_title,
)

_LOGGER = logging.getLogger(__name__)

# Laufzeit-Artefakte (YAML-Fallback) leben IM Integrationsordner, nicht im
# HA-Config-Root. So bleiben alle integrationsbezogenen Dateien beisammen.
_INTEGRATION_DIR = Path(__file__).resolve().parent
_DASH_FILE = "dashboard.yaml"
_LEGACY_DASH_DIR = "haier_bwwp"  # alter Ort unter <config>/ – wird aufgeräumt


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

    # Kompakter Einstellungen-Button: nur Zahnrad-Icon (niedrig), unter den
    # Schaltern – statt einer großen Kachel.
    settings_btn = {
        "type": "button",
        "name": "Einstellungen",
        "icon": "mdi:cog",
        "show_name": False,
        "tap_action": {
            "action": "navigate",
            "navigation_path": f"/config/integrations/integration/{DOMAIN}",
        },
    }
    steuerung = section("Steuerung", [
        tile("water_heater", "water_heater", "Brauchwasser",
             features=[{"type": "target-temperature"}]),
        tile("select", "mode", "Modus", features=[{"type": "select-options"}]),
        grid([
            tile("switch", "active", "Betrieb", features=[{"type": "toggle"}]),
            tile("switch", "boost", "Boost", features=[{"type": "toggle"}]),
            tile("switch", "mute", "Leise", features=[{"type": "toggle"}]),
            tile("switch", "sterilize", "Sterilisation", features=[{"type": "toggle"}]),
        ]),
        settings_btn,
    ])

    temps = section("Temperaturen", [grid([
        tile("sensor", "water_temp", "Wasser"),
        tile("sensor", "target_temp", "Ziel"),
        tile("sensor", "tank_top", "Tank oben"),
        tile("sensor", "tank_bottom", "Tank unten"),
        tile("sensor", "ambient", "Umgebung"),
        tile("sensor", "hotwater_pct", "Warmwasser"),
    ])])

    # PV-Karten nur sichtbar, wenn die PV-Steuerung aktiv ist: Sichtbarkeits-
    # Bedingung am Regel-Status-Sensor (steht bei Modus „Aus"/Executor auf „off").
    # So verschwinden die Kacheln dynamisch, wenn PV deaktiviert wird.
    pv_sensor = entry.options.get(CONF_PV_SENSOR)
    _pv_status_eid = eid("sensor", "pv_status")
    _pv_vis = (
        [{"condition": "state", "entity": _pv_status_eid, "state_not": "off"}]
        if _pv_status_eid else None
    )
    pv_tile = (
        {"type": "tile", "entity": pv_sensor, "name": "PV-Überschuss",
         "icon": "mdi:solar-power", **({"visibility": _pv_vis} if _pv_vis else {})}
        if pv_sensor else None
    )
    # "Aktuelle Quelle" prominent: großes, dynamisches Icon (vom Sensor) plus
    # dynamische Farbe via card-mod (--tile-color je aktiver Quelle). Die
    # einzelnen Bit-Kacheln (WP/Heizstab/Solar/Externe) entfallen.
    _cs_eid = eid("sensor", "current_source")
    _cs_color = (
        "ha-card { --tile-color: "
        "{% set s = state_attr('" + _cs_eid + "','active_sources') or [] %}"
        "{% if 'electric_heater' in s %}var(--orange-color)"
        "{% elif 'heat_pump' in s %}var(--green-color)"
        "{% elif 'solar' in s %}var(--amber-color)"
        "{% elif 'boiler' in s %}var(--red-color)"
        "{% else %}var(--disabled-color){% endif %}; }"
    ) if _cs_eid else None
    cs_extra = {"vertical": True, "card_mod": {"style": _cs_color}} if _cs_color else {"vertical": True}
    status = section("Status", [
        tile("sensor", "current_source", "Aktuelle Quelle", **cs_extra),
        grid([
            tile("binary_sensor", "connection", "Verbindung"),
            tile("sensor", "link_status", "Modbus-Status"),
            tile("sensor", "fault", "Fehlercode"),
        ]),
    ])

    # PV-Live-Status (nur wenn ein PV-Sensor konfiguriert ist): aktuelle
    # Regel-Stufe als Kachel + aktueller Überschuss, darunter der Tagesverlauf
    # der Sollwert-Wechsel als Logbuch (die Einträge, die pv.py schreibt).
    _set_temp_eid = eid("number", "set_temp")
    pv_logbook = {
        "type": "logbook",
        "title": "PV-Verlauf",
        "hours_to_show": 24,
        "entities": [e for e in (_set_temp_eid, _pv_status_eid) if e],
    } if (pv_sensor and (_set_temp_eid or _pv_status_eid)) else None
    pv_status_section = section("PV-Überschuss", [
        tile("sensor", "pv_status", "PV-Regelung", vertical=True),
        pv_logbook,
    ]) if pv_sensor else None
    if pv_status_section and _pv_vis:
        # Ganze PV-Sektion (inkl. Überschrift) ausblenden, wenn PV inaktiv.
        pv_status_section["visibility"] = _pv_vis

    # "Erfasst seit …"-Hinweis (dynamisches Datum aus dem 'seit'-Attribut).
    _heat_eid = eid("sensor", "total_heat")
    seit_md = {
        "type": "markdown",
        "content": (
            "{% set s = state_attr('" + _heat_eid + "','seit') %}"
            "Energie erfasst seit **{{ as_datetime(s).strftime('%d.%m.%Y') "
            "if s else 'Inbetriebnahme' }}**"
        ),
    } if _heat_eid else None

    energie = section("Energie & COP", [grid([
        tile("sensor", "cop_month", "COP (Monat)", color="green"),
        tile("sensor", "cop_year", "JAZ (Jahr)"),
        tile("sensor", "cop_prev_year", "JAZ (Vorjahr)"),
        tile("sensor", "total_heat", "Wärmemenge (gesamt)"),
        tile("sensor", "total_elec", "Strom gesamt"),
        tile("sensor", "heat_year", "Wärmemenge (akt. Jahr)"),
        tile("sensor", "hp_elec_year", "WP-Strom (Jahr)"),
        tile("sensor", "heater_elec_year", "Heizstab (Jahr)"),
        pv_tile,
    ]), seit_md])

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
    chart_day = statgraph("Energie pro Tag (30 Tage)", "day",
                          [("sensor", "total_heat"), ("sensor", "total_elec")])
    if chart_day:
        chart_day["days_to_show"] = 30
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
    # JAZ-Vergleich der letzten ~5 Jahre als Balken. Quelle: das Attribut
    # ``jaz_per_year`` der JAZ-(Jahr-)Entität (abgeschlossene Jahre) plus der
    # laufende Jahreswert aus dem State – zusammengeführt im data_generator.
    _cop_year_eid = eid("sensor", "cop_year")
    chart_jaz = {
        "type": "custom:apexcharts-card",
        "header": {"show": True, "title": "JAZ-Vergleich (Jahre)"},
        "graph_span": "1830d",
        "span": {"end": "year"},
        # Schmale Säulen (sonst füllt ein einzelner Jahreswert die ganze Breite).
        "apex_config": {"plotOptions": {"bar": {"columnWidth": "10%"}}},
        "series": [{
            "entity": _cop_year_eid,
            "name": "JAZ",
            "type": "column",  # apexcharts-card kennt kein chart_type: bar
            "data_generator": (
                "const h = entity.attributes.jaz_per_year || {}; "
                "let pts = Object.keys(h).map(y => [new Date(Number(y),0,1).getTime(), h[y].cop]); "
                "const cur = new Date().getFullYear(); const cv = parseFloat(entity.state); "
                "if(!isNaN(cv)) pts.push([new Date(cur,0,1).getTime(), cv]); "
                "const seen={}; pts.forEach(p => {seen[p[0]]=p[1];}); "
                "return Object.keys(seen).map(k => [Number(k),seen[k]]).sort((a,b)=>a[0]-b[0]);"
            ),
        }],
        "yaxis": [{"min": 0, "decimals": 2}],
    } if _cop_year_eid else None

    # Bedien-/Status-Kacheln oben; jedes Diagramm in EINER EIGENEN Sektion.
    # So bricht die Sections-Ansicht auf schmalen Schirmen (Smartphone) sauber
    # auf 1 Spalte um -> Diagramm = volle Breite/lesbar; am Desktop liegen sie
    # nebeneinander. (Ein horizontal-stack würde NICHT umbrechen und die Charts
    # auf dem Handy unleserlich quetschen.) Editierbarer Startpunkt.
    sections = [
        steuerung,
        temps,
        status,
        pv_status_section,
        energie,
        section(None, [chart_month]),
        section(None, [chart_day]),
        section(None, [chart_temp]),
        section(None, [chart_jaz]),
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


def _cleanup_legacy_dir(config_dir: str) -> None:
    """Alten ``<config>/haier_bwwp``-Ordner entfernen (best effort).

    Frühere Versionen legten den YAML-Fallback im HA-Config-Root ab. Der wandert
    jetzt in den Integrationsordner; der verwaiste Ordner wird hier aufgeräumt.
    """
    legacy = Path(config_dir) / _LEGACY_DASH_DIR
    if not legacy.is_dir():
        return
    try:
        old = legacy / _DASH_FILE
        if old.exists():
            old.unlink()
        legacy.rmdir()  # nur löschen, wenn leer – Fremd-Dateien bleiben erhalten
    except OSError:
        pass


def _remove_legacy_yaml_dashboard(hass: HomeAssistant) -> None:
    """Altes, gesperrtes YAML-Dashboard (``haier-bwwp``) aus der Seitenleiste nehmen.

    Bestehende Installationen hatten ein nicht editierbares YAML-Dashboard; das
    wird hier entfernt, damit nicht zwei Einträge nebeneinander stehen. Die
    YAML-Datei bleibt liegen (schadet nicht), wird aber nicht mehr registriert.

    Nur entfernen, wenn das Panel wirklich (noch) registriert ist – sonst loggt
    ``frontend.async_remove_panel`` bei jedem Start ein „Removing unknown panel
    haier-bwwp" als WARNING (das Panel ist längst weg). Das aktuelle Dashboard
    (``haier-hwhp``, Storage) bleibt davon unberührt.
    """
    if DASHBOARD_LEGACY_URL_PATH in hass.data.get("frontend_panels", {}):
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
    if not isinstance(dashboards, dict):
        return False

    # WICHTIG zuerst: existiert das Dashboard schon (Storage o. ä.)? Dann nichts
    # tun und True liefern -> der Aufrufer registriert KEIN YAML-Panel darüber.
    # (Die Collection wird nur zum NEU-Anlegen gebraucht; ihr Attributname ist
    # HA-versionsabhängig – sie hier zu früh zu verlangen, führte sonst zum
    # YAML-Fallback, der das editierbare Storage-Dashboard überdeckt hat.)
    if DASHBOARD_URL_PATH in dashboards:
        return True

    collection = (
        getattr(lovelace, "dashboards_collection", None)
        or getattr(lovelace, "dashboard_collection", None)
    )
    if collection is None:
        return False
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
            "title": localized_title(hass.config.language),
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
    # Schutz: niemals ein YAML-Panel über ein bereits existierendes (Storage-)
    # Dashboard legen – das würde den editierbaren Modus verdecken.
    lovelace = hass.data.get("lovelace")
    dashboards = getattr(lovelace, "dashboards", None)
    if isinstance(dashboards, dict) and DASHBOARD_URL_PATH in dashboards:
        return

    import yaml

    text = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    path = _INTEGRATION_DIR / _DASH_FILE
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
                "title": localized_title(hass.config.language),
                "icon": DASHBOARD_ICON,
                "show_in_sidebar": True,
                "require_admin": False,
            },
        )

    frontend.async_register_built_in_panel(
        hass,
        component_name="lovelace",
        sidebar_title=localized_title(hass.config.language),
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
        await hass.async_add_executor_job(_cleanup_legacy_dir, hass.config.path())
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
