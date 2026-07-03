# Changelog

Nennenswerte Änderungen dieser Integration. Format lose nach
[Keep a Changelog](https://keepachangelog.com/de/). Versionierung: **Feature = 2. Stelle**,
**Bugfix/Verfeinerung = 3. Stelle**. Vollständige Notizen auch in den
[GitHub-Releases](https://github.com/st03psn/haier-modbus/releases).

## [1.11.1] - 2026-07-03
- **Fehlercode als Klartext:** Der Sensor „Fehlercode" zeigt jetzt statt der rohen
  Registerzahl (z. B. `0`) einen lesbaren Text — `Kein Fehler` bzw. `E3 – Tank-
  Temperaturfühler: Kurzschluss/Unterbrechung`. Anzeige-Code (`code`) und Rohwert
  (`raw`) bleiben als Attribute erhalten, damit Automationen sprachunabhängig darauf
  triggern können. Icon wechselt fehlerfrei→Fehler. Entity-ID unverändert.

## [1.11.0] - 2026-06-28
- **PV-Steuerung mit Betriebsmodi** statt Bool-Haken: **Aus / Coordinator / Executor
  (HEMS-Client)** (Dropdown „PV-Modus"). Zweistufiger Dialog: erst der Modus, dann
  genau die Felder des gewählten Modus.
  - **Coordinator:** Integration regelt selbst nach **rohem** PV-Überschuss
    (`sensor.pv_uberschuss_watt`).
  - **Executor:** neue Entität `select.haier_hwhp_pv_program`
    (Aus/Grund/Überschuss/Boost) — ein externes HEMS (z. B. evcc) triggert die Programme;
    `pv.py` regelt nicht.
  - **Zweischichtige Regelung (gegen Takten):**
    - *WP-Zyklus* (Sollwert Grund↔Normal): fixer **Morgen-Start** (Default 10:00) als
      **einziger Kaltstart**/Tag; tagsüber Anhebung auf Normal **nur bei laufender WP**
      (Piggyback, über der **Halte-Schwelle** 50 W) → keine kurzen Nachmittags-Kaltstarts
      mehr. **Absenken** nach Entprellung (5 min), solange auch der Heizstab aus ist.
    - *Heizstab* (ad-hoc ab **Hoch-Schwelle**, **stoppt nie die WP**): **Boost** nur bei
      laufender WP, **ELEC** nur bei stehender WP (Dump nach dem Tageszyklus, danach zurück
      auf ECO + Grund-Sollwert). Geht der Überschuss weg, fällt nur der Heizstab weg
      (Sollwert Hoch→Normal/Grund); die WP läuft unverändert weiter.
    - Hoch-Schwelle-Default **1550 W** (Heizstab ~1500 W + Puffer); kein „Wiederanlauf"
      mehr (durch Piggyback ersetzt).
  - **Neuer Live-Status:** Diagnose-Sensor **„PV-Regelung Status"**
    (`sensor.haier_hwhp_pv_status`) — Aus / Grund / Normal (Piggyback) / Hoch + Boost /
    Hoch + ELEC, plus Attribute (Überschuss, Sollwert, WP läuft, Heizstab an). Im
    mitgelieferten Dashboard als **PV-Sektion** (Status-Kachel + Überschuss + Logbuch-
    Verlauf der Sollwert-Wechsel).
  - Entfernt: „verfügbar"-Modell mit BWWP-Leistungssensor + Hysterese (`pv_bwwp_sensor`,
    `pv_normal`, `pv_hysteresis`). **Migration:** alter Haken „an" → Coordinator, sonst Aus;
    alte Wiederanlauf-Schlüssel (`pv_reraise_threshold`/`pv_reraise_enabled`) werden entfernt.
  - `CONF_PV_HIGH`-Default 1500 → **1550 W** (jetzt Roh-Überschuss = Heizstab-Schwelle).
- Behoben: wiederkehrendes „Removing unknown panel haier-bwwp"-WARNING bei jedem Start
  (das alte Legacy-Panel wird nur noch entfernt, wenn es wirklich registriert ist).
- evcc-/HEMS-Anbindung (Executor) mit Beispiel-Automation: [`docs/pv-executor-evcc.md`](docs/pv-executor-evcc.md).

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
