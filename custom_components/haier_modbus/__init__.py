"""Haier BWWP (Modbus) – Integration-Setup."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)

from .const import (
    CONF_COP_ELEC_ENTITY,
    CONF_COP_ELEC_SOURCE,
    CONF_COP_HEAT_ENTITY,
    CONF_COP_HEAT_SOURCE,
    CONF_PV_BOOST,
    CONF_PV_ENABLED,
    CONF_PV_ESCALATION,
    CONF_PV_FORCE_ELEC,
    CONF_PV_MODE,
    DOMAIN,
    PLATFORMS,
    PV_ESC_BOOST,
    PV_ESC_ELEC,
    PV_MODE_COORDINATOR,
    PV_MODE_OFF,
    SOURCE_EXTERNAL,
    localized_title,
)
from .coordinator import HaierModbusCoordinator
from .dashboard import async_register_dashboard, async_remove_dashboard

_LOGGER = logging.getLogger(__name__)


class _PymodbusRetryNoise(logging.Filter):
    """Verschluckt pymodbus' transport-level 'No response received after N
    retries'-ERROR. Der Coordinator retryt bereits selbst (mit Reconnect) und
    führt den echten Verbindungszustand über den ``link_status``-Sensor – diese
    Zeile ist daher nur redundanter Lärm. Andere pymodbus-Fehler bleiben sichtbar.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return "No response received after" not in record.getMessage()


# Filter einmalig anhängen (idempotent – übersteht Reloads, kein Doppel-Filter).
_pymodbus_logger = logging.getLogger("pymodbus.logging")
if not any(isinstance(f, _PymodbusRetryNoise) for f in _pymodbus_logger.filters):
    _pymodbus_logger.addFilter(_PymodbusRetryNoise())


# (card_name, url_substring, hacs_repo, fs_fallback_path)
# ApexCharts -> JAZ/COP-/Verlaufsdiagramme; card-mod -> dynamische Farbe der
# "Aktuelle Quelle"-Kachel. Beide werden bei Bedarf via HACS nachgezogen.
_REQUIRED_FRONTEND_CARDS = [
    (
        "apexcharts-card",
        "apexcharts-card/apexcharts-card",
        "RomRider/apexcharts-card",
        "www/community/apexcharts-card/apexcharts-card.js",
    ),
    (
        "card-mod",
        "lovelace-card-mod/card-mod",
        "thomasloven/lovelace-card-mod",
        "www/community/lovelace-card-mod/card-mod.js",
    ),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up über einen Config-Entry.

    Bewusst kein ``async_config_entry_first_refresh`` (das würde einen
    Einrichtungsfehler/ConfigEntryNotReady auslösen, wenn der Modbus-Konverter
    beim Start nicht erreichbar ist). Stattdessen ein toleranter erster Refresh:
    Das Setup gelingt immer, eine Verbindungsstörung wird als Geräte-/Verbindungs-
    fehler dargestellt – Entitäten „nicht verfügbar", Binärsensor „Verbindung" = aus.
    Der Coordinator pollt weiter und verbindet selbsttätig neu, sobald der
    Konverter antwortet.
    """
    _migrate_legacy_options(hass, entry)

    coordinator = HaierModbusCoordinator(hass, entry)
    await coordinator.async_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Entity-IDs standardisieren (Bestand + Neuinstallation -> <domain>.haier_bwwp_<key>).
    _standardize_entity_ids(hass, entry)

    # Geräte-Energieregister ausblenden, wenn die jeweilige Quelle extern ist.
    _sync_device_register_visibility(hass, entry)

    # Mitgeliefertes Dashboard registrieren (Entitäten sind jetzt registriert).
    await async_register_dashboard(hass, entry)

    # Frontend-Karte (ApexCharts) sicherstellen – im Hintergrund, blockiert das
    # Setup nicht und kann es nie zum Scheitern bringen.
    entry.async_create_background_task(
        hass, _async_ensure_frontend_cards(hass), "haier_modbus_frontend_cards"
    )

    _async_register_services(hass)
    return True


SERVICE_RESET_ENERGY_STATS = "reset_energy_statistics"


def _async_register_services(hass: HomeAssistant) -> None:
    """Dienst zum Zurücksetzen der Energie-Langzeitstatistik (einmalig registriert).

    Hintergrund: Ein früherer Baseline-Seed-Bug ließ den Gesamt-Stromzähler
    einmalig auf den Lebenswert der Quelle springen; als ``total_increasing``
    trägt die Langzeitstatistik diesen Sprung als einmaligen Ausreißer mit.
    HA bietet dafür keinen eingebauten Dienst – dieser löscht gezielt die
    Langzeitstatistik der integrationseigenen Gesamt-Zähler (Wärme/Strom),
    danach baut der Recorder sie ab dem aktuellen (sauberen) Wert neu auf.
    """
    if hass.services.has_service(DOMAIN, SERVICE_RESET_ENERGY_STATS):
        return

    async def _handle_reset(call) -> None:
        reg = er.async_get(hass)
        stat_ids = [
            e.entity_id
            for e in reg.entities.values()
            if e.platform == DOMAIN
            and (e.unique_id.endswith("_total_heat") or e.unique_id.endswith("_total_elec"))
        ]
        if not stat_ids:
            _LOGGER.warning("Reset-Energie-Statistik: keine Gesamt-Zähler gefunden")
            return
        from homeassistant.components.recorder import get_instance

        get_instance(hass).async_clear_statistics(stat_ids)
        _LOGGER.info("Energie-Langzeitstatistik zurückgesetzt: %s", stat_ids)

    hass.services.async_register(DOMAIN, SERVICE_RESET_ENERGY_STATS, _handle_reset)


def _standardize_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Alle Entitäten dieses Eintrags auf ``<domain>.haier_bwwp_<key>`` umbenennen.

    Leitet das Ziel-Suffix aus der ``unique_id`` (``<entry_id>_<key>``) ab –
    generisch, ohne pro Entität etwas zu hardcoden. Greift einmalig (danach
    idempotent) und überspringt Kollisionen sowie bereits passende IDs.
    Hinweis: ändert bestehende entity_ids – Verweise auf alte IDs (Automationen/
    Karten) müssen ggf. angepasst werden.
    """
    reg = er.async_get(hass)
    prefix = f"{entry.entry_id}_"
    for ent in er.async_entries_for_config_entry(reg, entry.entry_id):
        uid = ent.unique_id or ""
        if not uid.startswith(prefix):
            continue
        suffix = uid[len(prefix):]
        obj = "haier_hwhp" if suffix == "water_heater" else f"haier_hwhp_{suffix}"
        desired = f"{ent.domain}.{obj}"
        if ent.entity_id == desired or reg.async_get(desired) is not None:
            continue
        try:
            reg.async_update_entity(ent.entity_id, new_entity_id=desired)
            _LOGGER.info("Entity-ID standardisiert: %s -> %s", ent.entity_id, desired)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Standardisierung von %s fehlgeschlagen: %s", ent.entity_id, exc)


def _sync_device_register_visibility(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Geräte-Energieregister-Sensoren je nach Quellenwahl ein-/ausblenden.

    Ist die Strom- bzw. Wärmequelle für COP **extern** konfiguriert, sind die
    entsprechenden Geräteregister redundant und unzuverlässig -> ausblenden
    (deaktivieren). Bei „Modbus" als Quelle wieder einblenden. Nur von der
    Integration deaktivierte Entitäten werden umgeschaltet – manuelle
    Nutzer-Entscheidungen (disabled_by=user) bleiben unangetastet.
    """
    elec_external = bool(entry.options.get(CONF_COP_ELEC_ENTITY))
    heat_external = bool(entry.options.get(CONF_COP_HEAT_ENTITY))
    hide_by_key = {
        "hp_elec_year": elec_external,
        "heater_elec_year": elec_external,
        "heat_year": heat_external,
    }
    reg = er.async_get(hass)
    for key, hide in hide_by_key.items():
        ent_id = reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")
        if not ent_id:
            continue
        ent = reg.async_get(ent_id)
        if ent is None:
            continue
        if hide and ent.disabled_by is None:
            reg.async_update_entity(ent_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION)
        elif not hide and ent.disabled_by == er.RegistryEntryDisabler.INTEGRATION:
            reg.async_update_entity(ent_id, disabled_by=None)


def _migrate_legacy_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Einmalige Bereinigung veralteter Options-Schlüssel (idempotent).

    1. COP-Quelle (ab v1.10.1): ergibt sich jetzt allein aus der gewählten
       Zähler-Entität (leer = Modbus, gesetzt = extern). Alte ``cop_*_source``
       entfernen; war die Quelle „Integriert", wird eine evtl. verwaiste
       Zähler-Entität mitgelöscht, damit sie nicht fälschlich als extern gilt.
    2. PV-Eskalation (ab v1.10.3): die zwei alten Booleans ``pv_boost`` /
       ``pv_force_elec`` werden zu einem Select ``pv_escalation`` zusammengeführt.
       Boost hat Vorrang vor ELEC, falls (widersprüchlich) beide gesetzt waren.
    3. PV-Modus (ab v1.11.0): der Bool-Haken ``pv_enabled`` wird zum Dropdown
       ``pv_mode`` (an -> ``coordinator``, aus/fehlt -> ``off``). Die alten
       „verfügbar"-Schlüssel (``pv_bwwp_sensor`` / ``pv_normal`` / ``pv_hysteresis``)
       und die Wiederanlauf-Schlüssel (``pv_reraise_threshold`` /
       ``pv_reraise_enabled``) entfallen – die neuen Defaults (Roh-Überschuss-
       Modell, Zwei-Schicht-Regelung) greifen stattdessen.

    Läuft genau einmal (danach sind die Alt-Keys weg, no-op).
    """
    o = dict(entry.options)
    changed = False

    for src_key, ent_key in (
        (CONF_COP_HEAT_SOURCE, CONF_COP_HEAT_ENTITY),
        (CONF_COP_ELEC_SOURCE, CONF_COP_ELEC_ENTITY),
    ):
        if src_key in o:
            if o.get(src_key) != SOURCE_EXTERNAL:
                o.pop(ent_key, None)
            del o[src_key]
            changed = True

    if CONF_PV_BOOST in o or CONF_PV_FORCE_ELEC in o:
        boost = bool(o.pop(CONF_PV_BOOST, False))
        force_elec = bool(o.pop(CONF_PV_FORCE_ELEC, False))
        if boost:
            o[CONF_PV_ESCALATION] = PV_ESC_BOOST
        elif force_elec:
            o[CONF_PV_ESCALATION] = PV_ESC_ELEC
        # sonst: keine Eskalation -> kein Key nötig (Default "none")
        changed = True

    # 3. PV-Modus: Bool-Haken -> Dropdown; alte verfügbar-/Wiederanlauf-Schlüssel entfernen.
    if CONF_PV_ENABLED in o:
        enabled = bool(o.pop(CONF_PV_ENABLED))
        o.setdefault(CONF_PV_MODE, PV_MODE_COORDINATOR if enabled else PV_MODE_OFF)
        changed = True
    for legacy in ("pv_bwwp_sensor", "pv_normal", "pv_hysteresis",
                   "pv_reraise_threshold", "pv_reraise_enabled"):
        if legacy in o:
            del o[legacy]
            changed = True

    if changed:
        hass.config_entries.async_update_entry(entry, options=o)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Bei Options-Änderung neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entladen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await async_remove_dashboard(hass)
        coordinator: HaierModbusCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_close()
    return unload_ok


def _missing_from_filesystem(config_dir_path: str) -> list[tuple[str, str, str]]:
    """Fallback: prüfe www/community/-Pfade, wenn der Resource-Store fehlt."""
    from pathlib import Path

    config_dir = Path(config_dir_path)
    return [
        (name, url_sub, repo)
        for name, url_sub, repo, fs_path in _REQUIRED_FRONTEND_CARDS
        if not (config_dir / fs_path).exists()
    ]


async def _async_ensure_frontend_cards(hass: HomeAssistant) -> None:
    """ApexCharts-Card vorhanden? Sonst via HACS nachziehen, sonst Repair-Hinweis.

    Nutzt die HACS-interne API (``hass.data['hacs']``) – inoffiziell, aber der
    übliche Weg. Alles gekapselt: schlägt etwas fehl, bleibt es bei einem
    Reparatur-Hinweis, das Setup ist nie betroffen.
    """
    try:
        # 1. Fehlende Karten ermitteln (Lovelace-Resource-Store, sonst Dateisystem).
        missing: list[tuple[str, str, str]] = []
        resources = hass.data.get("lovelace_resources")
        if resources is not None:
            try:
                urls = [item.get("url", "") for item in resources.async_items()]
                for name, url_sub, repo, _fs in _REQUIRED_FRONTEND_CARDS:
                    if not any(url_sub in url for url in urls):
                        missing.append((name, url_sub, repo))
            except Exception:  # noqa: BLE001
                missing = await hass.async_add_executor_job(
                    _missing_from_filesystem, hass.config.path()
                )
        else:
            missing = await hass.async_add_executor_job(
                _missing_from_filesystem, hass.config.path()
            )

        # 2. Vorhandene -> evtl. alten Repair-Hinweis löschen.
        present = {
            n for n, _, _, _ in _REQUIRED_FRONTEND_CARDS
        } - {m[0] for m in missing}
        for name in present:
            async_delete_issue(hass, DOMAIN, f"missing_frontend_card_{name.replace('-', '_')}")

        if not missing:
            return

        # 3. Auto-Install über HACS versuchen.
        installed: list[str] = []
        hacs = hass.data.get("hacs")
        still_missing = list(missing)
        if hacs is not None:
            still_missing = []
            for name, url_sub, repo_name in missing:
                try:
                    repo = hacs.repositories.get_by_full_name(repo_name)
                    if repo is None:
                        still_missing.append((name, url_sub, repo_name))
                        continue
                    if repo.data.installed:
                        continue
                    _LOGGER.info("Installiere Frontend-Karte %s via HACS …", name)
                    await repo.async_download_repository()
                    installed.append(name)
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.warning("HACS-Install für %s fehlgeschlagen: %s", name, exc)
                    still_missing.append((name, url_sub, repo_name))

        if installed:
            await hass.services.async_call(
                "persistent_notification", "create",
                {
                    "notification_id": "haier_modbus_frontend_installed",
                    "title": f"{localized_title(hass.config.language)} – Frontend-Karte installiert",
                    "message": (
                        f"Über HACS installiert: {', '.join(installed)}.\n\n"
                        "**Browser neu laden (Strg+Shift+R)**, um die Karte zu aktivieren."
                    ),
                },
                blocking=False,
            )

        # 4. Für nicht installierbare Karten einen Reparatur-Hinweis anlegen.
        for name, _url_sub, repo_name in still_missing:
            async_create_issue(
                hass,
                DOMAIN,
                f"missing_frontend_card_{name.replace('-', '_')}",
                is_fixable=False,
                severity=IssueSeverity.WARNING,
                translation_key="missing_frontend_card",
                translation_placeholders={"card_name": name, "hacs_repo": repo_name},
                learn_more_url="https://hacs.xyz/",
            )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("Frontend-Karten-Prüfung übersprungen: %s", exc)
