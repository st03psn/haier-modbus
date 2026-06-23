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
    CONF_COP_ELEC_SOURCE,
    CONF_COP_HEAT_SOURCE,
    DOMAIN,
    PLATFORMS,
    SOURCE_EXTERNAL,
)
from .coordinator import HaierModbusCoordinator
from .dashboard import async_register_dashboard, async_remove_dashboard

_LOGGER = logging.getLogger(__name__)

# (card_name, url_substring, hacs_repo, fs_fallback_path)
# Nur ApexCharts – wird von der mitgelieferten JAZ/COP-Vergleichskarte benötigt.
_REQUIRED_FRONTEND_CARDS = [
    (
        "apexcharts-card",
        "apexcharts-card/apexcharts-card",
        "RomRider/apexcharts-card",
        "www/community/apexcharts-card/apexcharts-card.js",
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
    return True


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
        obj = "hwhp" if suffix == "water_heater" else f"hwhp_{suffix}"
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
    elec_external = entry.options.get(CONF_COP_ELEC_SOURCE) == SOURCE_EXTERNAL
    heat_external = entry.options.get(CONF_COP_HEAT_SOURCE) == SOURCE_EXTERNAL
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
                    "title": "Haier BWWP – Frontend-Karte installiert",
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
