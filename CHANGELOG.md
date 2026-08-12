# Changelog

Nennenswerte Änderungen dieser Integration. Format lose nach
[Keep a Changelog](https://keepachangelog.com/de/). Versionierung: **Feature = 2. Stelle**,
**Bugfix/Verfeinerung = 3. Stelle**. Vollständige Notizen auch in den
[GitHub-Releases](https://github.com/st03psn/haier-modbus/releases).

## [1.16.1] - 2026-08-12
- **Morgen-Start heizt nicht mehr aus dem Netz auf Erhöht.** Der fixe Morgen-Start schrieb
  bedingungslos die Erhöht-Zieltemperatur (65 °C) und schaltete auf AUTO – ohne den
  Überschuss anzusehen. An trüben Tagen kam damit die gesamte Ladung aus dem Netz.
  Neu: Der Morgen-Start schreibt die **Basis-Zieltemperatur in ECO** und macht damit eine
  effiziente Grundladung. Die Anhebung auf Erhöht + AUTO folgt erst bei Überschuss über
  den bestehenden Piggyback-Zweig – und **ohne** ein weiteres Startkontingent zu
  verbrauchen, weil die Wärmepumpe dann bereits läuft (kein neuer Verdichterstart).
  Wirksam ist das Schreiben der Basis, weil die Nachtabsenkung (1.16.0) den Sollwert
  zuvor auf `pv_night_floor` gedrückt hat.
- **Temperatur-Diagramm zeigt die Umgebungstemperatur wieder.** Die Y-Achse hatte eine
  harte Untergrenze von 35 °C – die Umgebungskurve lag damit vollständig unterhalb des
  sichtbaren Bereichs und stand nur noch in der Legende. Neu sind weiche Grenzen
  (`~0` bis `~75`): 0–75 °C sind immer sichtbar, die Achse wächst aber mit, wenn Werte
  darüber oder darunter liegen (z. B. Frost). **Hinweis:** Das Dashboard wird nur
  **einmalig** angelegt, damit eigene Anpassungen erhalten bleiben – bestehende
  Dashboards übernehmen die neue Achse nicht automatisch (Karte von Hand anpassen oder
  das Dashboard löschen, damit es neu erzeugt wird).
- **Kaltstart-Schwelle `pv_coldstart` auf 600 W** (vorher 500 W) – maximale
  Verdichteraufnahme mit etwas Puffer. Gemessen wird dabei der Überschuss **ohne**
  laufende Wärmepumpe, weil der Verdichter beim Kaltstart noch steht.

> **Hinweis zum Release `v1.16.0`:** Das GitHub-Release mit diesem Tag wurde versehentlich
> auf einem älteren Commit (Stand 1.14.0) erzeugt, bevor der zugehörige PR gemergt war –
> es enthält **nicht** die unten beschriebenen Änderungen und kann übersprungen werden.
> Der vollständige Stand von 1.16.0 ist in **1.16.1** enthalten.

## [1.16.0] - 2026-08-12
- **PV-Regelstufen überarbeitet: vier klar getrennte Stufen** (`base` -> `Erhöht` ->
  `Boost`, ELEC separat als Notfall). Grundlage: Code-Analyse + 10 Tage Verlaufsdaten
  einer realen HP200M7-F9.
  - **Solar-Boost-Stufe entfernt** (AP1): In der Praxis-Konfiguration war ihr Ziel
    identisch mit Erhöht (`min(pv_temp_high, 65) == pv_temp_normal`) – eine wirkungslose
    Stufe. `CONF_PV_SOLAR_BOOST`/die zugehörige Number-Entität entfallen.
  - **Boost ist jetzt eine Leistungssenke, keine eigene Temperaturstufe** (AP2): Die
    Zieltemperatur bei Boost ist dieselbe wie bei Erhöht. `pv_temp_high` bleibt nur noch
    für das Executor-Programm relevant.
  - **Strikte Bezugsvermeidung für den Heizstab** (AP3, der inhaltliche Kern): Der
    Überschusssensor ist einspeisungsbasiert – der Heizstab senkte beim Einschalten
    seinen eigenen Messwert und taktete dadurch potenziell mit der doppelten
    Entprellzeit. Neu: `verfügbar = roher Überschuss + (Heizstab an ? P_heizstab : 0)`,
    macht das Signal invariant gegen die eigene Schalthandlung. `pv_high` bekommt dadurch
    eine einzige, klare Bedeutung (Nennleistung + Reserve, Default jetzt **1600 W** statt
    1550 W) und wird laufzeitgeklemmt, falls die Konfiguration das unterschreitet. Neue
    Optionen `pv_heater_power` (Nennleistung, Default 1500 W) und optional
    `pv_power_entity` (Geräte-Gesamtleistung, für eine gemessene statt geschätzte
    Heizstableistung). Zusätzlich **asymmetrische Entprellung**: Einschalten weiter mit
    voller Entprellzeit (Schutz gegen Sensor-Ausreißer bis 13 kW, real belegt),
    Ausschalten sofort (ein Poll) – kein Bezug soll entstehen, während der Überschuss
    schon unter der Schwelle liegt.
  - **Modusführung ECO/AUTO** (AP4): `base` schreibt jetzt aktiv ECO, `Erhöht`/`Boost`
    aktiv AUTO (statt sich auf das geräteeigene ECO-Zeitfenster zu verlassen). Harte
    Invariante: AUTO nur mit Sollwert ≤ 65 °C (oberhalb zieht das Gerät laut Datenblatt
    selbsttätig den Heizstab) – mit Boost == Erhöht-Ziel konstruktiv erfüllt. Tritt
    zurück, wenn Legionellen-Schutz oder Notheizung den Modus besitzen.
  - **ELEC raus aus der PV-Eskalation** (AP5): Reg 1 ist ein Modus-*Wert*, kein Bitfeld –
    "ELEC als Bit schalten" gibt es nicht. ELEC ist jetzt ausschließlich eine
    Notfall-Option in `emergency.py` (neue Option `emergency_mode`: `auto` [Standard] |
    `elec`). Alte `pv_escalation: elec`-Konfigurationen werden automatisch auf `boost`
    migriert.
  - **Tagesplan: ein Lauf, Nachtabsenkung, Verdichterschonung** (AP6): Neuer
    überschussgetriebener **Tages-Kaltstart** (`pv_coldstart`, Default 500 W) ergänzt den
    fixen Morgen-Start – beide teilen sich ein Tageskontingent (`pv_max_starts`, Default
    1: "möglichst ein Lauf/Tag"). Der Anti-Takt-Guard gilt jetzt für **jede** Anhebung bei
    stehender WP, nicht mehr nur für den Morgen-Start. Endet ein Zyklus, fällt der
    Sollwert **sofort** auf die Basis-Zieltemperatur zurück (auch mitten am Tag) – der
    Tagesplan bleibt so verbindlich. Neue **Nachtabsenkung** (`pv_night_floor`, Default
    45 °C): ab dem Rückfall bis zum nächsten Start ein Sollwert-Boden statt der
    Basis-Zieltemperatur, damit das Gerät nicht mehr ohne Sonne in die Nacht nachheizt
    (belegt: Nachheizung um 4 Uhr ohne jeden Überschuss). Der harte Boden bleibt
    unverändert die Notheizung (kritische Temperatur).
  - **PV-Status kennt nur noch** `off` / `base` / `normal` (Erhöht) / `boost` / `manual` /
    `held` – `solar_boost` und `high_elec` entfallen, `high_boost` heißt jetzt `boost`.

## [1.15.0] - 2026-08-11
- **Stufen folgen jetzt der echten Gerätegrenze (65 °C WP / 75 °C mit Heizstab).**
  Aufbauend auf der in 1.14.1 dokumentierten Datenblatt-Angabe:
  - **Normal- und Erhöht-Zieltemperatur sind auf 65 °C begrenzt** (Auswahl im Dialog und
    an den `number`-Entitäten) — diese Stufen muss der **Verdichter allein** erreichen.
  - **Die Boost-Zieltemperatur bleibt bis 75 °C wählbar** — nur dort hilft der Heizstab.
  - **Die Solar-Boost-Stufe zielt jetzt auf `min(Boost-Ziel, 65 °C)`** statt stur auf die
    Boost-Zieltemperatur. Vorher hätte die WP bei einem Boost-Ziel von 75 °C ein Ziel
    angesteuert, das sie **nie allein erreichen kann**.
  - Ergebnis ist eine saubere 4-Stufen-Kaskade, z. B. bei **50 / 60 / 75 °C**:
    `Normal 50 → Erhöht 60 → Solar-Boost 65 (WP allein an der Grenze) → Boost 75
    (Heizstab schiebt darüber)`. Beim Absenken fällt zuerst der Heizstab weg, dann Stufe
    für Stufe. Der Heizstab verbraucht damit **keine kWh mehr für eine Spanne, die der
    Verdichter auch geschafft hätte**.
- **Plausibilitätsprüfung der Zieltemperaturen:** Der Konfigurationsdialog weist
  `Erhöht ≤ Normal` und `Boost < Erhöht` jetzt mit einer verständlichen Meldung zurück,
  statt die Stufen stillschweigend kollabieren zu lassen (die Laufzeit-Klemmung in `pv.py`
  bleibt als zweites Netz bestehen).
- **Boost ist wieder das, was der Name sagt: WP + Heizstab gemeinsam.** Die in 1.14.0
  eingeführte Wartebedingung („Heizstab erst, wenn die WP ihre Grenze erreicht hat")
  entfällt — ab der Boost-Schwelle wird der deutliche Überschuss **direkt der laufenden
  WP zugeschaltet**, ohne Verzögerung. Damit ist die Stufenfolge durchgängig:
  **base** (Standard) → **Erhöht** (leichter Überschuss) → **Solar-Boost** (mehr
  Überschuss, WP allein bis 65 °C) → **Boost** (deutlicher Überschuss, WP + Heizstab bis
  75 °C). *Nur Heizstab (ELEC)* bleibt davon getrennt die Schnellaufheiz-/Notfall-Option
  bei **stehender** WP.
- **Negativpreis-Sensor mit neuer Rolle:** Ist er „an", greift **Boost bereits ab der
  Solar-Boost-Schwelle** statt erst ab der Boost-Schwelle (Einspeisung ist im Fenster
  unvergütet). Neu dokumentierter Vorbehalt: **nur mit dynamischem Stromtarif sinnvoll** —
  ein negativer Börsenpreis senkt den Einspeiseerlös, nicht automatisch den Bezugspreis;
  reicht der Überschuss nicht für den Heizstab (~1500 W), kommt der Rest aus dem Netz.

## [1.14.1] - 2026-08-11
- **Doku: Gerätegrenzen dokumentiert** (neu: [`docs/geraete-grenzen.md`](docs/geraete-grenzen.md)).
  Kernpunkt: Das Hersteller-Datenblatt der M7-Reihe nennt zwei **getrennte** Zeilen —
  **Einstellbereich *mit Heizstab* 35–75 °C** gegenüber **max. Temperaturausgabe *nur
  Wärmepumpe* 65 °C**. Der Bereich 65–75 °C ist also nur mit dem **1500-W-Heizstab**
  (COP ≈ 1) erreichbar; die geräteeigene Sterilisation heizt 1×/Woche auf 75 °C.
  Damit ist die **Boost-Zieltemperatur** praktisch auf **65 °C** zu
  setzen, sonst kann die Solar-Boost-Stufe (Verdichter allein) ihr Ziel nie erreichen.
  Empfohlene Staffelung **50 / 58–60 / 65 °C**; für den Legionellen-Schutz
  `legionella_bottom_min` **60 °C** statt 65 (Nachweis an der kältesten Schicht).
  Enthält außerdem Feldmessungen: 4 Monate Maximum 65 °C, und ein messbarer
  Kapazitätsabfall von ≈ 6,0 K/h (53→59 °C) auf ≈ 3,9 K/h (60→65 °C).
  Hinweise dazu jetzt auch im README (DE/EN) und als Kommentar an
  `DEFAULT_PV_TEMP_HIGH`. **Keine Verhaltensänderung** — reine Dokumentation.
- **Neu: `CLAUDE.md`** mit Architektur-Überblick, harten Regeln (kein zweiter Bus-Master,
  nur FC 0x10, eine Quelle der Wahrheit, `LIVE_OPTION_KEYS` statt Reload) und den
  Regelungs-Fallstricken, die in der Vergangenheit reale Fehler verursacht haben.

## [1.14.0] - 2026-08-11
- **Verdichter vor Heizstab („Solar-Boost"):** Der WP-Zyklus (Schicht 1, Coordinator) ist
  jetzt **3-stufig** — Normal → Erhöht → **Solar-Boost**. Über der neuen Schwelle
  **„Solar-Boost"** (Default 600 W, konfigurierbar) klettert der Zyklus — weiterhin nur bei
  bereits laufender WP (Piggyback, kein zusätzlicher Kaltstart) — selbst bis auf die
  **Boost-Zieltemperatur** (Default 75 °C), rein über den Verdichter. Der **Heizstab**
  (Schicht 2, Variante *Boost*) schaltet erst zu, wenn die WP diese Stufe **bereits selbst
  erreicht** hat und weiterhin genug Überschuss übrig ist; bisher sprang er beim
  Überschreiten der Boost-Schwelle sofort mit an. Hintergrund: Der Heizstab wandelt
  Überschuss 1:1 um (COP ≈ 1), der Verdichter erreicht dasselbe Ziel mit COP i. d. R. 3–4×
  — und der von der WP nicht gezogene Überschuss bleibt (vergütet) einspeisbar.
  *Nebenwirkung: Der Heizstab startet dadurch bis zu zwei Entprellzeiten später — gewollt.*
  **Absenken** erfolgt jetzt schrittweise über die mittlere Stufe (Solar-Boost → Erhöht →
  Normal). **ELEC** (Heizstab bei stehender WP, Dump nach dem Tageszyklus) bleibt
  unverändert. Neuer Diagnose-Zustand **„Solar-Boost (nur WP)"** im Status-Sensor.
- **Optionaler Negativpreis-Sensor:** Neues (leer lassbares) Feld für einen
  `binary_sensor`/`input_boolean`, der die aktuelle Viertelstunde als Negativ-/Null-Preis
  kennzeichnet (Solarspitzengesetz/§51 EEG; z. B. eigenes Template über Tibber/aWATTar/
  Nordpool — die Integration berechnet den Preis nicht selbst). Ist er „an", darf der
  Heizstab schon **vor** Erreichen der Solar-Boost-Stufe zuschalten: Einspeisung ist in dem
  Fenster ohnehin unvergütet, und der schneller volle Speicher lässt später am Tag mehr
  **vergüteten** Überschuss übrig. Leer = unverändertes Verhalten.
- **PV-Schwellen direkt auf der Geräteseite:** Zieltemperaturen (Normal/Erhöht/Boost) und
  Überschuss-Schwellen (Halte/Solar-Boost/Heizstab) gibt es zusätzlich als eigene Entitäten
  (`number.haier_hwhp_pv_*`, Kategorie *Konfiguration*) — dieselbe Quelle wie der
  „Konfigurieren"-Dialog, nur ohne Umweg über den mehrstufigen Dialog. Die
  Zieltemperaturen erscheinen auch im **Executor**-Modus (das Programm-Select nutzt sie),
  die Watt-Schwellen nur im **Coordinator**-Modus. Sie bleiben auch bei Modbus-Störung
  bedienbar.
- **Kein Reload mehr bei reinen Schwellen-Änderungen:** Diese Werte liest die PV-Steuerung
  ohnehin bei jedem Poll frisch; ein Reload war unnötig und **schädlich** — er verwarf
  interne Besitzstände ohne Persistenz und konnte dadurch das **Boost-Bit dauerhaft gesetzt**
  bzw. das Gerät **in ELEC hängen** lassen, den manuellen Sollwert-Schutz vergessen und
  einen laufenden Legionellen-Lauf abbrechen. Änderungen an diesen Schwellen laufen jetzt
  reload-frei; alle anderen Options-Änderungen laden weiterhin normal neu.
- **Robustheit gegen verdrehte Schwellen:** Zieltemperaturen und Überschuss-Schwellen werden
  intern in eine gültige Reihenfolge geklemmt, und ein Sicherheitsventil verhindert, dass
  eine Konfiguration, in der die Leiter den Deckel nie erreicht, den Heizstab **dauerhaft
  aussperrt**.
- Dashboard: Temperatur-Diagramm reicht jetzt bis **80 °C** (vorher 60 °C — der Sollwert
  klippte bereits bei 65 °C).

## [1.13.2] - 2026-08-10
- **Config-Änderung unterbricht keinen laufenden PV-Zyklus mehr:** Jede
  Options-Änderung lädt die Integration komplett neu, wodurch auch die
  PV-Steuerung (Coordinator-Modus) neu startet. Bisher hat sie dabei den
  vorgefundenen Sollwert anhand der (ggf. gerade geänderten) Zieltemperaturen
  neu einsortiert — reduzierte man z. B. die Normaltemperatur, während gerade
  ein Erhöht-Zyklus lief, wurde dieser **mitten im Lauf** auf den neuen,
  niedrigeren Wert abgesenkt statt zu Ende zu fahren. Der beim Reload
  vorgefundene Sollwert wird jetzt unverändert übernommen; läuft die WP zu dem
  Zeitpunkt bereits, bleibt er für den **gesamten Rest dieses Laufs** stehen —
  eine (ggf. neue) Config greift erst normal, sobald die WP wieder aus ist.
  Neuer Zwischenzustand **„Laufender Zyklus gehalten"** im Diagnose-Sensor
  „PV-Regelung Status".

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
