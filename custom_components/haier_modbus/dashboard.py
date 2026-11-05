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

import hashlib
import json
import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    CONF_DASHBOARD_ENABLED,
    CONF_DASHBOARD_IMAGE,
    CONF_HEAT_EXCHANGER,
    CONF_MODEL,
    DEFAULT_HEAT_EXCHANGER,
    DEFAULT_MODEL_KEY,
    HEAT_EXCHANGER_NO,
    HEAT_EXCHANGER_YES,
    MODEL_HEIGHT_MM,
    MODELS_WITH_COIL,
    CONF_PV_MODE,
    DASHBOARD_ICON,
    DASHBOARD_LEGACY_URL_PATH,
    DASHBOARD_COMPARE_URL_PATH,
    DASHBOARD_URL_PATH,
    DEFAULT_DASHBOARD_ENABLED,
    DEFAULT_PV_MODE,
    DOMAIN,
    PV_MODE_EXECUTOR,
    PV_MODE_OFF,
    localized_title,
)
from .dashboard_layout import build_layout

_LOGGER = logging.getLogger(__name__)

# Laufzeit-Artefakte (YAML-Fallback) leben IM Integrationsordner, nicht im
# HA-Config-Root. So bleiben alle integrationsbezogenen Dateien beisammen.
_INTEGRATION_DIR = Path(__file__).resolve().parent
_DASH_FILE = "dashboard.yaml"
_LEGACY_DASH_DIR = "haier_bwwp"  # alter Ort unter <config>/ – wird aufgeräumt

# Layout-Generation des mitgelieferten Dashboards. Ein bestehendes (Nutzer-)
# Dashboard wird NIE automatisch überschrieben; ist die gespeicherte Generation
# älter, gibt es einmalig einen Hinweis auf den Dienst ``rebuild_dashboard``.
DASHBOARD_LAYOUT_VERSION = 3  # 2 = Ein-Seiten-Layout ab v2.0.0, 3 = Geräteabbild (#29)
_LAYOUT_STORE_KEY = f"{DOMAIN}.dashboard_layout"
_NOTIFY_ID = f"{DOMAIN}_dashboard_layout"  # nur noch zum Entfernen (2.0.0)
DASHBOARD_ISSUE_ID = "dashboard_layout_update"
# Gleicher Hinweis/Ablauf, eigener Text: Grafik-Variante (Modell/Optionen) geändert.
DASHBOARD_VARIANT_ISSUE_KEY = "dashboard_variant_update"


def _show_coil(setting: str, model: str) -> bool:
    """Rohrschlange zeigen? „auto“ = nach Modell (Register-Varianten …M7C-F9)."""
    if setting == HEAT_EXCHANGER_YES:
        return True
    if setting == HEAT_EXCHANGER_NO:
        return False
    return model in MODELS_WITH_COIL


def _variant(entry: ConfigEntry | None) -> str | None:
    """Fingerabdruck der Speicher-Grafik (Bauform, Rohrschlange, eigenes Bild).

    Ändert er sich (Modell- oder Optionswechsel), bekommt ein angepasstes Dashboard
    den Reparatur-Hinweis – ein unverändertes wird ohnehin still neu geschrieben.
    """
    if entry is None:
        return None
    model = entry.options.get(CONF_MODEL, entry.data.get(CONF_MODEL, DEFAULT_MODEL_KEY))
    height = MODEL_HEIGHT_MM.get(model, MODEL_HEIGHT_MM[DEFAULT_MODEL_KEY])
    coil = _show_coil(entry.options.get(CONF_HEAT_EXCHANGER, DEFAULT_HEAT_EXCHANGER), model)
    return f"{height}|{int(coil)}|{entry.options.get(CONF_DASHBOARD_IMAGE, '')}"


def _build_config(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Dashboard-Config mit real aufgelösten entity_ids bauen (Layout: dashboard_layout)."""
    reg = er.async_get(hass)

    def resolve(domain: str, key: str) -> str | None:
        ent_id = reg.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")
        if not ent_id:
            return None
        ent = reg.async_get(ent_id)
        if ent is not None and ent.disabled_by is not None:
            return None  # deaktivierte Entitäten (z. B. Solar/Kessel) nicht aufnehmen
        return ent_id

    pv_mode = entry.options.get(CONF_PV_MODE, DEFAULT_PV_MODE)
    model = entry.options.get(CONF_MODEL, entry.data.get(CONF_MODEL, DEFAULT_MODEL_KEY))
    return build_layout(
        resolve,
        hass.config.language,
        with_pv=pv_mode != PV_MODE_OFF,
        executor=pv_mode == PV_MODE_EXECUTOR,
        settings_path=f"/config/integrations/integration/{DOMAIN}",
        height_mm=MODEL_HEIGHT_MM.get(model, MODEL_HEIGHT_MM[DEFAULT_MODEL_KEY]),
        coil=_show_coil(entry.options.get(CONF_HEAT_EXCHANGER, DEFAULT_HEAT_EXCHANGER), model),
        image=entry.options.get(CONF_DASHBOARD_IMAGE, ""),
    )


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


def _find_dashboards_collection(hass: HomeAssistant, lovelace):
    """Lovelace-Dashboard-Collection finden (#18).

    Seit mindestens HA 2026.2 hält ``LovelaceData`` die Collection nicht mehr
    (Felder nur noch ``dashboards``, ``resource_mode``, ``resources``,
    ``yaml_dashboards``); sie ist in ``lovelace.async_setup`` eine lokale
    Variable. Erreichbar bleibt sie über den registrierten Websocket-Befehl
    ``lovelace/dashboards/list``: dessen Handler ist die gebundene Methode
    ``ws_list_item`` von ``StorageCollectionWebsocket``, das die Collection als
    ``storage_collection`` hält (geprüft im HA-Quellcode 2026.2.3 und 2026.11.0).
    Ältere Versionen mit Attribut an ``LovelaceData`` werden weiter bedient.
    Ohne Treffer -> None, der Aufrufer fällt auf YAML zurück.
    """
    for attr in ("dashboards_collection", "dashboard_collection"):
        coll = getattr(lovelace, attr, None)
        if coll is not None:
            return coll
    handlers = hass.data.get("websocket_api")
    if not isinstance(handlers, dict):
        return None
    for command in ("lovelace/dashboards/list", "lovelace/dashboards/create"):
        entry = handlers.get(command)
        handler = entry[0] if isinstance(entry, tuple) and entry else None
        for _ in range(5):  # Dekoratoren (functools.wraps) abwickeln
            if handler is None:
                break
            coll = getattr(getattr(handler, "__self__", None), "storage_collection", None)
            if coll is not None and hasattr(coll, "async_create_item"):
                return coll
            handler = getattr(handler, "__wrapped__", None)
    return None


async def _seed_storage_dashboard(hass: HomeAssistant, config: dict) -> str | None:
    """Editierbares Storage-Dashboard EINMALIG anlegen.

    Gibt None zurück, wenn ein Storage-Dashboard existiert (neu angelegt ODER
    bereits vorhanden – dann bleiben die Anpassungen des Nutzers unangetastet).
    Greift auf die interne Lovelace-Collection zu; bei abweichender API wird
    ein kurzer Grund (str) geliefert, den der Aufrufer protokolliert, bevor er
    auf YAML zurückfällt (#18: bisher war unsichtbar, WARUM der Rückfall griff).
    """
    lovelace = hass.data.get("lovelace")
    if lovelace is None:
        return "hass.data['lovelace'] fehlt"
    dashboards = getattr(lovelace, "dashboards", None)
    if not isinstance(dashboards, dict):
        return f"lovelace.dashboards ist kein dict ({type(lovelace).__name__})"

    # WICHTIG zuerst: existiert das Dashboard schon (Storage o. ä.)? Dann nichts
    # tun und True liefern -> der Aufrufer registriert KEIN YAML-Panel darüber.
    # (Die Collection wird nur zum NEU-Anlegen gebraucht; ihr Attributname ist
    # HA-versionsabhängig – sie hier zu früh zu verlangen, führte sonst zum
    # YAML-Fallback, der das editierbare Storage-Dashboard überdeckt hat.)
    if DASHBOARD_URL_PATH in dashboards:
        return None

    collection = _find_dashboards_collection(hass, lovelace)
    if collection is None:
        attrs = sorted(a for a in dir(lovelace) if not a.startswith("_"))
        return (
            f"keine Dashboard-Collection an {type(lovelace).__name__} "
            f"(mode={getattr(lovelace, 'mode', '?')}, Attribute: {', '.join(attrs)})"
        )
    try:
        items = list(collection.async_items())
    except Exception:  # noqa: BLE001
        items = []
    if any((i or {}).get("url_path") == DASHBOARD_URL_PATH for i in items):
        return None

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
        return "Dashboard angelegt, aber kein Storage-Objekt registriert"
    await store.async_save(config)  # Start-Layout hinterlegen
    return None


def _is_own_yaml_dashboard(dashboards, url_path: str) -> bool:
    """True, wenn unter ``url_path`` unser YAML-Rückfall hängt (kein Storage)."""
    dash = dashboards.get(url_path) if isinstance(dashboards, dict) else None
    if dash is None:
        return False
    cfg = getattr(dash, "config", None) or {}
    filename = str(cfg.get("filename", "")) if isinstance(cfg, dict) else ""
    return filename == str(_INTEGRATION_DIR / _DASH_FILE)


def _remove_own_yaml_dashboard(hass: HomeAssistant) -> None:
    """YAML-Rückfall abmelden (Dashboard per Option abgeschaltet, #18).

    Ein editierbares Storage-Dashboard bleibt unangetastet – das gehört dem
    Nutzer und lässt sich in den Einstellungen löschen.
    """
    lovelace = hass.data.get("lovelace")
    dashboards = getattr(lovelace, "dashboards", None)
    if not _is_own_yaml_dashboard(dashboards, DASHBOARD_URL_PATH):
        return
    dashboards.pop(DASHBOARD_URL_PATH, None)
    if DASHBOARD_URL_PATH in hass.data.get("frontend_panels", {}):
        try:
            frontend.async_remove_panel(hass, DASHBOARD_URL_PATH)
        except Exception:  # noqa: BLE001
            pass
    _LOGGER.info("Haier-YAML-Dashboard abgemeldet (Option „Dashboard anlegen“ aus)")


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
        if not entry.options.get(CONF_DASHBOARD_ENABLED, DEFAULT_DASHBOARD_ENABLED):
            _remove_own_yaml_dashboard(hass)
            _publish_status(hass, None)
            return
        config = _build_config(hass, entry)
        existed = DASHBOARD_URL_PATH in _dashboards(hass)
        reason = await _seed_storage_dashboard(hass, config)
        if reason is None:
            _LOGGER.info(
                "Editierbares Haier-Dashboard unter /%s", DASHBOARD_URL_PATH
            )
            await _async_sync_layout(hass, config, existed, entry)
            return
        await _register_yaml_dashboard(hass, config)
        _publish_status(hass, DASHBOARD_LAYOUT_VERSION)  # YAML wird je Start neu erzeugt
        # WARNING statt INFO (#18): Der Rückfall ist nicht editierbar und kommt
        # bei jedem Start wieder – der Nutzer soll Grund und Ausweg sehen.
        _LOGGER.warning(
            "Haier-Dashboard nur als NICHT editierbares YAML unter /%s angelegt – "
            "Storage-Dashboard nicht möglich: %s. Abschalten über die Option "
            "„Dashboard automatisch anlegen“ der Integration.",
            DASHBOARD_URL_PATH,
            reason,
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Dashboard-Registrierung übersprungen: %s", exc)


def _config_hash(config: dict | None) -> str | None:
    if not isinstance(config, dict):
        return None
    raw = json.dumps(config, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


LAYOUT_SIGNAL = f"{DOMAIN}_dashboard_layout"
LAYOUT_STATUS_KEY = f"{DOMAIN}_dashboard_layout"


def _dashboards(hass: HomeAssistant) -> dict:
    dashboards = getattr(hass.data.get("lovelace"), "dashboards", None)
    return dashboards if isinstance(dashboards, dict) else {}


def _publish_status(hass: HomeAssistant, applied: int | None) -> None:
    """Stand für Update-Entität und Buttons bereitstellen (None = kein Dashboard verwaltet)."""
    hass.data[LAYOUT_STATUS_KEY] = {
        "applied": applied,
        "latest": DASHBOARD_LAYOUT_VERSION,
        "compare": DASHBOARD_COMPARE_URL_PATH in _dashboards(hass),
    }
    async_dispatcher_send(hass, LAYOUT_SIGNAL)


async def _async_sync_layout(
    hass: HomeAssistant, config: dict, existed: bool, entry: ConfigEntry | None = None
) -> None:
    """Mitgeliefertes Layout aktuell halten, ohne Nutzer-Anpassungen zu überschreiben.

    Gespeichert (``.storage/haier_modbus.dashboard_layout``):
      ``applied``  Layout-Generation, die zuletzt ins Dashboard geschrieben wurde
      ``hash``     Fingerabdruck dieses geschriebenen Dashboards
      ``declined`` Generation, die der Nutzer im Reparatur-Hinweis abgelehnt hat
      ``variant``  Grafik-Variante (``_variant``: Bauform, Rohrschlange, Bild), mit der
                   das Dashboard zuletzt geschrieben wurde (ab 2.1.0, #29);
                   ``pending_variant``/``declined_variant`` für den Hinweis
      (``notified`` stammt aus 2.0.0 und wird nicht mehr ausgewertet)
    Entspricht das gespeicherte Dashboard noch dem Fingerabdruck, hat der Nutzer
    nichts verändert -> es wird still auf das aktuelle Layout gebracht. Sonst
    bleibt es unangetastet; ist seine Generation älter, meldet die Update-Entität
    ``update.<…>_dashboard`` ein Update (dauerhaft sichtbar unter Einstellungen
    und – im neuen Layout – als Kachel im Dashboard), und unter *Reparaturen*
    fragt ein Hinweis mit Ja/Nein (``repairs.py``), bis er beantwortet ist.
    Dashboards vor v2.0.0 haben keinen Fingerabdruck und gelten als angepasst
    (Generation 1). Ist die Generation aktuell, aber die Grafik-Variante gewechselt
    (z. B. anderes Modell), fragt derselbe Hinweis mit eigenem Text; „Nein“ gilt
    dann für diese Variante.
    """
    meta_store: Store = Store(hass, 1, _LAYOUT_STORE_KEY)
    meta = await meta_store.async_load() or {}
    new_hash = _config_hash(config)
    variant = _variant(entry)
    if not existed:  # gerade frisch angelegt
        await meta_store.async_save({**meta, "applied": DASHBOARD_LAYOUT_VERSION, "hash": new_hash,
                                     "notified": DASHBOARD_LAYOUT_VERSION, "variant": variant})
        _publish_status(hass, DASHBOARD_LAYOUT_VERSION)
        return

    dashboards = _dashboards(hass)
    dash = dashboards.get(DASHBOARD_URL_PATH)
    if dash is None or _is_own_yaml_dashboard(dashboards, DASHBOARD_URL_PATH):
        _publish_status(hass, DASHBOARD_LAYOUT_VERSION)  # YAML wird je Start neu erzeugt
        return
    try:
        current = await dash.async_load(False)
    except Exception:  # noqa: BLE001 – z. B. noch leer
        current = None
    cur_hash = _config_hash(current)

    if meta.get("hash") and cur_hash == meta["hash"]:
        if cur_hash != new_hash:
            await dash.async_save(config)
            _LOGGER.info("Unverändertes Haier-Dashboard auf aktuelles Layout gebracht")
        await meta_store.async_save({**meta, "applied": DASHBOARD_LAYOUT_VERSION, "hash": new_hash,
                                     "notified": DASHBOARD_LAYOUT_VERSION, "variant": variant})
        _publish_status(hass, DASHBOARD_LAYOUT_VERSION)
        return

    applied = int(meta.get("applied", 1))
    _publish_status(hass, applied)
    # Benachrichtigung aus 2.0.0 ablösen – der Hinweis steht jetzt unter Reparaturen.
    await hass.services.async_call(
        "persistent_notification", "dismiss", {"notification_id": _NOTIFY_ID}, blocking=False
    )
    layout_due = (
        applied < DASHBOARD_LAYOUT_VERSION
        and int(meta.get("declined", 0)) < DASHBOARD_LAYOUT_VERSION
    )
    # #29: Layout aktuell, aber Grafik-Variante gewechselt (Modell/Optionen). Fehlt die
    # gespeicherte Variante (Dashboards vor 2.1.0), wird nicht gefragt.
    variant_due = (
        not layout_due
        and applied >= DASHBOARD_LAYOUT_VERSION
        and meta.get("variant") not in (None, variant)
        and meta.get("declined_variant") != variant
    )
    if entry is None or not (layout_due or variant_due):
        ir.async_delete_issue(hass, DOMAIN, DASHBOARD_ISSUE_ID)
        return
    if meta.get("pending_variant") != variant:
        await meta_store.async_save({**meta, "pending_variant": variant})
    # Reparatur-Hinweis mit Ja/Nein (repairs.py). Nicht persistent: wird je Start neu
    # angelegt, solange weder übernommen noch abgelehnt wurde.
    ir.async_create_issue(
        hass,
        DOMAIN,
        DASHBOARD_ISSUE_ID,
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=DASHBOARD_VARIANT_ISSUE_KEY if variant_due else DASHBOARD_ISSUE_ID,
        data={"entry_id": entry.entry_id},
    )


async def async_decline_layout(hass: HomeAssistant) -> None:
    """„Nein“ im Reparatur-Hinweis: für diese Layout-Generation nicht mehr fragen.

    Das Update „Dashboard“ unter Einstellungen bleibt bestehen (dort überspringbar),
    Übernehmen ist weiterhin über Optionen → Dashboard möglich.
    """
    meta_store: Store = Store(hass, 1, _LAYOUT_STORE_KEY)
    meta = await meta_store.async_load() or {}
    await meta_store.async_save({**meta, "declined": DASHBOARD_LAYOUT_VERSION,
                                 "declined_variant": meta.get("pending_variant")})
    ir.async_delete_issue(hass, DOMAIN, DASHBOARD_ISSUE_ID)


async def async_rebuild_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Dienst ``rebuild_dashboard``: mitgeliefertes Layout neu schreiben.

    Ersetzt den Inhalt des Haier-Dashboards (Storage) durch das aktuelle Layout –
    eigene Anpassungen gehen dabei verloren (bewusste Nutzeraktion). Fehlt das
    Dashboard, wird es wie beim Setup angelegt.
    """
    config = _build_config(hass, entry)
    dashboards = _dashboards(hass)
    store = dashboards.get(DASHBOARD_URL_PATH)
    if store is None or _is_own_yaml_dashboard(dashboards, DASHBOARD_URL_PATH):
        _remove_own_yaml_dashboard(hass)
        await async_register_dashboard(hass, entry)
    else:
        await store.async_save(config)
    meta_store: Store = Store(hass, 1, _LAYOUT_STORE_KEY)
    meta = await meta_store.async_load() or {}
    await meta_store.async_save(
        {**meta, "applied": DASHBOARD_LAYOUT_VERSION, "hash": _config_hash(config),
         "notified": DASHBOARD_LAYOUT_VERSION, "variant": _variant(entry)}
    )
    _publish_status(hass, DASHBOARD_LAYOUT_VERSION)
    ir.async_delete_issue(hass, DOMAIN, DASHBOARD_ISSUE_ID)
    _LOGGER.info("Haier-Dashboard auf Layout %s neu aufgebaut", DASHBOARD_LAYOUT_VERSION)


async def async_create_compare_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Neues Layout als zusätzliches Dashboard zum Vergleich anlegen (bzw. neu schreiben).

    Das bestehende Haier-Dashboard bleibt unverändert. Der Fingerabdruck des
    erzeugten Vergleichs-Dashboards wird gemerkt, damit „übernehmen“ erkennt, ob
    der Nutzer es vorher angepasst hat.
    """
    config = _build_config(hass, entry)
    dashboards = _dashboards(hass)
    store = dashboards.get(DASHBOARD_COMPARE_URL_PATH)
    if store is None:
        collection = _find_dashboards_collection(hass, hass.data.get("lovelace"))
        if collection is None:
            raise HomeAssistantError("Lovelace-Dashboard-Liste nicht gefunden")
        de = (hass.config.language or "en").lower().startswith("de")
        await collection.async_create_item(
            {
                "url_path": DASHBOARD_COMPARE_URL_PATH,
                "title": f"{localized_title(hass.config.language)} ({'neu' if de else 'new'})",
                "icon": DASHBOARD_ICON,
                "show_in_sidebar": True,
                "require_admin": False,
            }
        )
        store = _dashboards(hass).get(DASHBOARD_COMPARE_URL_PATH)
        if store is None:
            raise HomeAssistantError("Vergleichs-Dashboard wurde nicht registriert")
    await store.async_save(config)
    meta_store: Store = Store(hass, 1, _LAYOUT_STORE_KEY)
    meta = await meta_store.async_load() or {}
    await meta_store.async_save({**meta, "compare_hash": _config_hash(config),
                                 "compare_variant": _variant(entry)})
    _publish_status(hass, (hass.data.get(LAYOUT_STATUS_KEY) or {}).get("applied"))
    _LOGGER.info("Vergleichs-Dashboard unter /%s angelegt", DASHBOARD_COMPARE_URL_PATH)


async def async_promote_compare_dashboard(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Vergleichs-Dashboard zum Standard machen (inkl. eigener Änderungen daran).

    Kopiert den Inhalt nach ``/haier-hwhp`` und entfernt das Vergleichs-Dashboard.
    War es unverändert, verwaltet die Integration das Dashboard danach wieder
    automatisch; wurde es angepasst, gilt das Ergebnis als angepasst (geschützt).
    """
    dashboards = _dashboards(hass)
    compare = dashboards.get(DASHBOARD_COMPARE_URL_PATH)
    if compare is None:
        raise HomeAssistantError("Kein Vergleichs-Dashboard vorhanden")
    config = await compare.async_load(False)
    main = dashboards.get(DASHBOARD_URL_PATH)
    if main is None or _is_own_yaml_dashboard(dashboards, DASHBOARD_URL_PATH):
        raise HomeAssistantError("Haier-Dashboard ist kein editierbares Dashboard")
    await main.async_save(config)

    meta_store: Store = Store(hass, 1, _LAYOUT_STORE_KEY)
    meta = await meta_store.async_load() or {}
    cfg_hash = _config_hash(config)
    unchanged = bool(meta.get("compare_hash")) and cfg_hash == meta.get("compare_hash")
    meta.pop("compare_hash", None)
    variant = meta.pop("compare_variant", None) or _variant(entry)
    await meta_store.async_save({**meta, "applied": DASHBOARD_LAYOUT_VERSION,
                                 "hash": cfg_hash if unchanged else None,
                                 "notified": DASHBOARD_LAYOUT_VERSION, "variant": variant})

    collection = _find_dashboards_collection(hass, hass.data.get("lovelace"))
    if collection is not None:
        item_id = next(
            (iid for iid, item in getattr(collection, "data", {}).items()
             if (item or {}).get("url_path") == DASHBOARD_COMPARE_URL_PATH),
            None,
        )
        if item_id is not None:
            await collection.async_delete_item(item_id)
    _publish_status(hass, DASHBOARD_LAYOUT_VERSION)
    ir.async_delete_issue(hass, DOMAIN, DASHBOARD_ISSUE_ID)
    _LOGGER.info("Vergleichs-Dashboard übernommen (angepasst: %s)", not unchanged)


async def async_remove_dashboard(hass: HomeAssistant) -> None:
    """Beim Entladen NICHTS löschen.

    Das Storage-Dashboard gehört nun dem Nutzer (Drag&Drop-Anpassungen) und
    bleibt über Reloads/Neustarts erhalten. Ein evtl. YAML-Fallback-Panel wird
    beim nächsten Setup ohnehin mit ``update=True`` neu registriert.
    """
    return
