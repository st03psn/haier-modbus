# Changelog

Nennenswerte Änderungen dieser Integration. Format lose nach
[Keep a Changelog](https://keepachangelog.com/de/). Versionierung: **Feature = 2. Stelle**,
**Bugfix/Verfeinerung = 3. Stelle**. Vollständige Notizen auch in den
[GitHub-Releases](https://github.com/st03psn/haier-modbus/releases).

## [Unreleased]
### Geplant
- **PV-Steuerung mit Betriebsmodi** statt Bool-Haken: **Aus / Coordinator / Executor
  (HEMS-Client)**. Coordinator = Integration regelt selbst (Roh-Überschuss-Modell +
  pünktlicher Morgen-Start + optionaler Wiederanlauf). Executor = Integration stellt
  Programme (Aus/Grund/Überschuss/Boost) bereit, ein externes HEMS (z. B. evcc) triggert
  sie. Plan: [`docs/pv-rework-plan.md`](docs/pv-rework-plan.md).

## [1.10.6] - 2026-06-26
- Eigenes Integrations-Icon mitgeliefert (`custom_components/haier_modbus/brand/`); HA 2026.3+
  lädt lokale Brand-Bilder bevorzugt — kein `home-assistant/brands`-PR mehr nötig.

## [1.10.5] - 2026-06-26
- PV-Hochstufe standardmäßig **75 °C** (Geräte-Maximum, Reg 6), zuvor 70.

## [1.10.4] - 2026-06-26
- Doppelte Erklärung bei der Notfall-Nachheizung entfernt (Feld-Labels gekürzt).

## [1.10.3] - 2026-06-26
- PV-Eskalation als **ein Dropdown** (Keine / Boost / Nur Heizstab) statt zwei sich
  widersprechender Haken; einmalige Options-Migration.

## [1.10.2] - 2026-06-26
- Doku/Hinweis: PV-Steuerung setzt externe **Watt-Sensoren** voraus; BWWP-Leistungssensor
  von „optional" auf „empfohlen".

## [1.10.1] - 2026-06-26
- COP-Quellenwahl vereinfacht: ergibt sich aus der gewählten Zähler-Entität
  (leer = integriertes Modbus-Register) — die zwei Quellen-Dropdowns entfallen; einmalige Migration.
- `pv.py` schreibt **HA-Logbuch-Einträge** bei jedem Stufenwechsel.

## [1.10.0] - 2026-06-26
- PV-Überschuss-Steuerung **in die Integration konsolidiert** (`pv.py`): „verfügbarer
  Solarstrom"-Modell (PV + WP-Aufnahme) mit Hysterese + Anti-Takt, komplett im
  „Konfigurieren"-Dialog einstellbar. Mitgelieferter PV-**Blueprint entfernt**.

## [1.9.0] - 2026-06-26
- PV-Blueprint überarbeitet: dynamisches „verfügbarer Solarstrom"-Modell + Hysterese +
  **Anti-Kurztakt-Schutz** (Mindest-Stillstand + Piggyback). Fix: kaputter `!input`-Trigger
  im Blueprint. (Kumulativ aus den Zwischenständen 1.7.2/1.8.0.)

## [1.7.1] und früher (≤ 2026-06-25)
- Siehe die [GitHub-Releases](https://github.com/st03psn/haier-modbus/releases) (u. a. v1.7.1
  Log-Spam-Filter, v1.7.0 Auto-Install card-mod, v1.6.x dynamisches Quellen-Icon, COP/JAZ-Akkumulator).
