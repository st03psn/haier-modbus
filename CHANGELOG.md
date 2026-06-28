# Changelog

Nennenswerte Änderungen dieser Integration. Format lose nach
[Keep a Changelog](https://keepachangelog.com/de/). Versionierung: **Feature = 2. Stelle**,
**Bugfix/Verfeinerung = 3. Stelle**. Vollständige Notizen auch in den
[GitHub-Releases](https://github.com/st03psn/haier-modbus/releases).

## [1.11.0] - 2026-06-28
- **PV-Steuerung mit Betriebsmodi** statt Bool-Haken: **Aus / Coordinator / Executor
  (HEMS-Client)** (Dropdown „PV-Modus").
  - **Coordinator:** Integration regelt selbst nach **rohem** PV-Überschuss
    (`sensor.pv_uberschuss_watt`) — fixer **Morgen-Start** (Default 10:00), **Halten**
    über der Halte-Schwelle (50 W), **Absenken** nach Entprellung (5 min), optionaler
    **Wiederanlauf** (200 W, Anti-Takt), **75 + Eskalation** (Boost/ELEC) ab Hoch-Schwelle
    (1200 W). Halte-/Wiederanlauf-/Morgen-Felder neu konfigurierbar.
  - **Executor:** neue Entität `select.haier_hwhp_pv_program`
    (Aus/Grund/Überschuss/Boost) — ein externes HEMS (z. B. evcc) triggert die Programme;
    `pv.py` regelt nicht.
  - **Zweischichtige Regelung (gegen Takten):**
    - *WP-Zyklus* (Sollwert 50↔60): Morgen-Start als **einziger Kaltstart**/Tag; tagsüber
      Anhebung auf Normal **nur bei laufender WP** (Piggyback) → keine kurzen Nachmittags-
      Kaltstarts mehr.
    - *Heizstab* (ad-hoc ab Hoch-Schwelle, **stoppt nie die WP**): **Boost** nur bei
      laufender WP, **ELEC** nur bei stehender WP (Dump nach dem Tageszyklus, danach zurück
      auf ECO + Grund-Sollwert). Geht der Überschuss weg, fällt nur der Heizstab weg
      (Sollwert Hoch→Normal/Grund); die WP läuft unverändert weiter.
    - „Wiederanlauf-Schwelle"/„Tages-Wiederanlauf" entfallen (durch Piggyback ersetzt);
      Hoch-Schwelle-Default **1550 W** (Heizstab ~1500 W + Puffer).
  - Entfernt: „verfügbar"-Modell mit BWWP-Leistungssensor + Hysterese (`pv_bwwp_sensor`,
    `pv_normal`, `pv_hysteresis`). **Migration:** alter Haken „an" → Coordinator, sonst Aus.
  - `CONF_PV_HIGH`-Default 1500 → **1200 W** (jetzt Roh-Überschuss).
- Plan/Referenz (inkl. evcc-Beispiel): [`docs/pv-rework-plan.md`](docs/pv-rework-plan.md).

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
