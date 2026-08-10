# Changelog

Nennenswerte Änderungen dieser Integration. Format lose nach
[Keep a Changelog](https://keepachangelog.com/de/). Versionierung: **Feature = 2. Stelle**,
**Bugfix/Verfeinerung = 3. Stelle**. Vollständige Notizen auch in den
[GitHub-Releases](https://github.com/st03psn/haier-modbus/releases).

## [1.13.1] - 2026-08-10
- **Manueller Sollwert-Eingriff (PV-Coordinator) wird jetzt zuverlässig erkannt:**
  Die seit v1.12.0 bestehende „manueller Eingriff wird respektiert"-Erkennung
  griff nicht, wenn die PV-Steuerung seit dem letzten Neustart/Reload noch nie
  selbst einen Sollwert geschrieben hatte (z. B. weil der Sollwert ohnehin schon
  beim PV-Ziel stand). In dem Fall blieb die interne Baseline (`_last_written`)
  dauerhaft leer, wodurch der **allererste** manuelle Eingriff (Display/HA) nicht
  als „manuell" galt und beim nächsten Poll-Zyklus (Default 5 s, oft konfiguriert
  auf mehr) **stillschweigend überschrieben** wurde – beobachtet als: Sollwert
  manuell erhöht, WP läuft kurz an, dann schreibt die PV-Steuerung sofort wieder
  auf ihr eigenes Ziel zurück, WP geht wieder aus. Die Baseline wird jetzt beim
  ersten Auswerten nach dem Start/Reload aus dem aktuellen Register-Sollwert
  gesetzt, sodass auch der erste manuelle Eingriff korrekt erkannt und bis zum
  nächsten Morgen-Start in Ruhe gelassen wird.

## [1.13.0] - 2026-07-30
- **Legionellen-Schutz (periodische thermische Desinfektion):** Neue optionale
  Funktion nach dem **Watchdog-Prinzip** – überwacht wird nur die eine
  sicherheitsrelevante Größe: *wie lange ist die letzte vollständige Durchheizung
  her?* Erreicht der Speicher nicht innerhalb des Intervalls (Default **7 Tage**)
  am **Boden** (`Tank unten`, kälteste Schicht) die Zieltemperatur, wird ein
  Desinfektionslauf erzwungen: Sollwert temporär auf **65 °C**, bevorzugt im
  **ECO-Fenster** (Default 10–18 Uhr) effizient mitheizend, mit Eskalation auf
  **AUTO**, damit das Ziel garantiert erreicht wird (**kein Timeout/Abbruch** –
  der Lauf endet nur bei nachgewiesenem Erfolg). Erfolg = `Tank unten` hält die
  Nachweis-Schwelle (Default 60 °C) für die Haltezeit (Default 30 min); danach
  wird der vorherige Sollwert/Modus wiederhergestellt.
  - **Selbst-Reset:** Wird der Speicher zwischendurch ohnehin voll durchgeheizt
    (z. B. PV-Boost auf 65/75 °C), zählt das als Desinfektion und der Timer
    springt zurück – im Alltag mit täglicher Nutzung läuft also kaum ein
    Extra-Zyklus, der Schutz greift v. a. bei Stagnation (Urlaub).
  - **Neuer Diagnose-Sensor** „Legionellen-Schutz" (`sensor.haier_hwhp_legionella_status`):
    Geschützt / Fällig / Desinfektion läuft / Haltephase, plus Attribute (letzte
    Volldurchheizung, Tage seither, nächste Fälligkeit, Tank unten, Ziel).
  - **Koordination:** Während eines Laufs pausiert die PV-Sollwert-Regelung und
    die Notheizung tritt zurück (kein Schreibkonflikt); danach übernehmen sie
    wieder normal. Persistiert (letzte Volldurchheizung übersteht HA-Neustarts).
  - Alles im „Konfigurieren"-Dialog einstellbar (Intervall, Ziel, Nachweis-
    Schwelle Tank unten, Haltezeit, bevorzugtes Fenster). **Verbrühgefahr:** bei
    65 °C ein thermostatisches Mischventil vorsehen.

## [1.12.2] - 2026-07-30
- **Notfall-Nachheizung erreicht jetzt die Zieltemperatur:** Die Rück-Schwelle
  `recover` (Standard 48 °C) wurde als fester Absolutwert ausgewertet – unabhängig
  vom Sollwert. Lag sie *unter* dem Sollwert (z. B. 48 °C bei Sollwert 50 °C bzw.
  60 °C in der PV-Regelung), gab die Notheizung schon **vor** Erreichen der
  Zieltemperatur von AUTO an ECO zurück – und zwar genau in die **ECO-Totzone**
  (knapp unter dem Sollwert, aber über der geräteinternen Wiedereinschaltschwelle).
  ECO sprang dann **trotz offenem Zeitfenster** nicht wieder an, die Wärmepumpe
  blieb aus und das Warmwasser kühlte über Stunden aus (beobachtet: Rückschaltung
  bei 48 °C mitten im 10–18-Uhr-Fenster, danach Absinken bis ~32 °C). Die
  Rück-Schwelle wird jetzt nie unter den aktuellen Sollwert (Reg 6) gelegt
  (`max(recover, Sollwert)`), sodass die Notheizung bis mindestens zur
  Zieltemperatur in AUTO nachheizt. `recover` bleibt als eigenes Feld erhalten und
  wirkt unverändert, sobald es ≥ Sollwert konfiguriert ist.

## [1.12.1] - 2026-07-20
- **COP/Energie stürzt nach Zähler-Aussetzer nicht mehr ab:** Kehrte ein externer
  Strom-/Wärmezähler aus `unavailable` mit einem minimal kleineren (gerundeten)
  Wert zurück — z. B. `547.315837` → `547.315` —, wertete die interne
  Delta-Akkumulation diesen winzigen Rückschritt fälschlich als **Zähler-Reset**
  und rechnete den **gesamten Zählerstand** als Verbrauch ein. Ein einzelner
  0,0008-kWh-Blip blähte so die Strom-Eimer um mehrere hundert kWh auf und ließ
  den COP (Monat/Jahr) auf physikalisch unmögliche Werte (< 1) einbrechen. Ein
  Rückschritt gilt jetzt — wie in HA für `total_increasing` üblich — erst ab
  über 10 % Einbruch als echter Reset; kleinere Rückschritte (Rundung, Rückkehr
  aus „nicht verfügbar", Mess-Jitter) werden als 0 verworfen.
- **Einmalige Neu-Baseline:** Bereits verfälschte Monats-/Jahres-/Gesamt-Eimer
  werden beim ersten Start dieser Version einmalig aus den (sauberen) Quell-
  Statistiken bzw. Geräteregistern neu geseedet, sodass COP und Energiewerte
  sich sofort erholen. Der bestehende Dienst `haier_modbus.reset_energy_statistics`
  bereinigt zusätzlich den Ausreißer in der Langzeitstatistik der Gesamt-Zähler
  (Energie-Dashboard / „Energie pro Tag").

## [1.12.0] - 2026-07-10
- **Manueller Temperatur-Eingriff wird respektiert:** Ändert man die Solltemperatur
  von Hand — am Gerätedisplay oder über HA — überschreibt die PV-Steuerung
  (Coordinator-Modus) sie nicht mehr sofort zurück. Der Eingriff gilt **bis zum
  nächsten Morgen-Start**, dann übernimmt die Regelung wieder. Erkannt wird jeder
  Wert, der von der PV-Steuerung nicht selbst geschrieben wurde (Display **und** HA).
  Die Heizstab-/Boost-Schicht läuft weiter — nur der Sollwert bleibt in Ruhe. Der
  Diagnose-Sensor „PV-Regelung Status" zeigt währenddessen `Manueller Eingriff`.
- **PV-Regelungsstufen umbenannt** in **Normal / Erhöht / Boost** (vorher
  Grund / Normal / Hoch): betrifft die Anzeigetexte des Diagnose-Sensors
  „PV-Regelung Status" (`Boost` bzw. `Boost (ELEC)` für die beiden Heizstab-
  Mechaniken) sowie die Zieltemperatur-Felder im Options-Dialog
  („Normal-/Erhöht-/Boost-Zieltemperatur"). Interne Zustände/Keys und die
  Executor-Programme (`select`) bleiben unverändert.

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
