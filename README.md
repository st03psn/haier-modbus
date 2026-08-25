# Haier Brauchwasserwärmepumpe (Modbus) · Haier Heat-Pump Water Heater (Modbus)

> 🇩🇪 **Deutsch zuerst** · 🇬🇧 [English version below](#-english)

Lokale Home-Assistant-Integration für die Haier Brauchwasserwärmepumpe der
**M7-Familie** (HP160/HP200/HP260 M7, R290) über **Modbus-TCP** – mit
**Schreibzugriff**, Energie-/COP-Auswertung und mitgeliefertem, editierbarem
Dashboard. Anzeigename je nach Systemsprache: **„Haier BWWP"** (Deutsch),
sonst **„Haier HWHP"** (Englisch).

Vollständig **lokal** über Modbus – kein hOn-Cloud-Konto nötig. Gegenüber der
Cloud bietet der lokale Weg **Schreibzugriff**, direkten Zugriff auf die
**Energieregister** und läuft **ohne Internet-/Cloud-Abhängigkeit**.

---

## ⚠️ Wichtig: Hat dein Gerät überhaupt Modbus?

**Nicht jede** Brauchwasserwärmepumpe dieser Serie besitzt die Modbus-Schnittstelle.
Inoffiziell ist sie **erst ab Produktionsdatum ~April 2025** verbaut. So prüfst du es:

- Im **Geräte-/Service-Menü** oder im **Handbuch** nachsehen, ob es einen Punkt
  zur **Modbus-/Slave-ID-Konfiguration** gibt. Ist dieser vorhanden, unterstützt
  dein Gerät Modbus; dort wird auch die **Slave-ID** (Standard `1`) eingestellt.

**Benötigte Hardware:**
- Die native Schnittstelle ist **Modbus RTU über RS485** (9600 Baud, 8N1).
- Du brauchst einen **Modbus-RTU→TCP-Konverter (Gateway)** im Netzwerk; Home
  Assistant verbindet sich mit dessen **IP-Adresse auf Port 502** (nicht mit der
  Wärmepumpe direkt).
- Das **RS485-Kabel** von der Wärmepumpe (Klemmen A/B, ggf. GND) zum Konverter
  muss man sich i. d. R. **selbst konfektionieren**. Die genaue Klemmen-/
  Anschlussbelegung steht im Handbuch; praktische Hinweise und Erfahrungen im
  Community-Thread:
  [haustechnikdialog.de – Brauchwasserwärmepumpe Haier R290](https://www.haustechnikdialog.de/Forum/t/285616/Brauchwasserwaermepumpe-Haier-R290).

> Hinweis: Schreibbare Register akzeptieren nur FC `0x10` (Mehrfach-Write); ein
> einzelnes `0x06` lehnt das Gerät ab. Das erledigt die Integration intern.

---

## Funktionen

- **Einrichtungs-Assistent** (Verbindung + Modell → COP → optional PV-Überschuss);
  später alles unter **Konfigurieren** änderbar (inkl. Host/Port/Slave).
- **Zweisprachig** – Entitätsnamen folgen der Nutzersprache; Geräte-/Dashboard-Name
  der Systemsprache (DE „Haier BWWP", sonst „Haier HWHP").
- **Steuerung (RW):** Solltemperatur, Modus (AUTO/ECO/ELEC/VAC), Schalter
  Aktiv/Boost/Leise/Sterilisation.
- **Aktuelle Quelle:** kombinierte, dynamische Anzeige aus dem Statusregister
  (z. B. „Wärmepumpe", „Wärmepumpe + Heizstab", „Solar", „Externe Wärmequelle"),
  mit wechselndem Icon. Attribute `active_sources`/`status_register` für Automationen.
- **Sensoren:** Wasser-/Ziel-/Tank-/Umgebungstemperatur, Warmwasser %, Modus-Text,
  **Fehlercode** (mit Klartext, siehe unten).
- **Energie & COP:** gerätegemessene Register + **berechneter COP/JAZ** mit frei
  wählbaren Quellen (Modbus-intern oder externer Zähler wie Shelly).
- **Diagnose:** **Modbus-Status** (`OK` / `Konverter nicht erreichbar` /
  `Gerät antwortet nicht`) und Binärsensor **Verbindung**.
- **PV-Überschuss-Steuerung** eingebaut (optional): Modi Aus / Coordinator / Executor (HEMS-Client).
- **Notfall-Nachheizung** (optional): schaltet bei kritisch niedriger Wassertemperatur
  vorübergehend auf AUTO oder ELEC, unabhängig vom ECO-Zeitfenster. Details unten.
- **Legionellen-Schutz** (optional): periodische thermische Desinfektion nach
  Watchdog-Prinzip, mit Nachweis über die Bodentemperatur. Details unten.
- **Editierbares Dashboard** (Storage-Modus) wird automatisch angelegt.
- **Ein Block-Read** (Register 1–90) je Intervall (Standard 5 s).

## Installation (HACS)

1. HACS → ⋮ → **Benutzerdefinierte Repositorys** → URL dieses Repos, Kategorie **Integration**.
2. Herunterladen, Home Assistant neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen** → „Haier".
4. **Verbindung:** Host = **IP des Modbus-Konverters** (nicht der WP), Port `502`,
   Slave `1`, Intervall `5`, Modell.
5. **COP/Energie:** Quellen wählen. 6. **PV (optional):** Sensor + Schwellen.

Alternativ lokal: Ordner `custom_components/haier_modbus/` nach
`<config>/custom_components/` kopieren und neu starten.

## COP / JAZ

### System-COP vs. Geräte-COP (wichtig)
Der ausgewiesene COP/JAZ ist ein **System-COP**: bei externer Stromquelle (Shelly)
steckt die **real gemessene** Energie drin – **inkl. Standby, Steuerelektronik
und Lüfter**. Der **geräteinterne** Zähler bilanziert nur den
**Betriebsverbrauch** (ohne Nebenverbraucher/Standby), ist auf ganze kWh gerundet
und liegt erfahrungsgemäß **deutlich zu niedrig** → der Geräte-COP fällt zu
optimistisch aus. **Für eine belastbare JAZ einen externen Stromzähler nutzen.**
Details: [`docs/register-map.md`](docs/register-map.md).

### Kalender-ausgerichtete Fenster
Die geräteinternen „dieses Jahr"-Register von Strom und Wärme resetten zu
*unterschiedlichen* Zeitpunkten. Die Integration zählt beide in **gemeinsame
Monats-/Jahres-Fenster** (utility_meter-Logik, reset-fest). Daraus: **`COP (Monat)`**,
**`JAZ (Jahr)`**, **`JAZ (Vorjahr)`** sowie monotone Gesamt-Zähler
**`Wärmemenge (gesamt)`** / **`Stromverbrauch (gesamt)`** (für Verbrauchskurven;
Attribut `seit` = Start der Erfassung). Jahreswerte werden beim Jahreswechsel
archiviert (Attribut `jaz_per_year`) und im Dashboard als **JAZ-Vergleich** gezeigt.

### Energie-Statistik zurücksetzen
Bei einem einmaligen Ausreißer in den Diagrammen: Dienst
**`haier_modbus.reset_energy_statistics`** (Entwicklerwerkzeuge → Aktionen) löscht
die Langzeitstatistik der Gesamt-Zähler und baut sie sauber neu auf. **Betrifft
beide Zähler** (Wärme + Strom); deren bisherige Tages-/Monatshistorie geht verloren.

## Fehlercodes
Register 18 liefert eine Zahl, die gruppenweise auf die Anzeige-Codes abbildet
(`1–15 E.., 16–31 L.., 32–47 F.., 48–63 P.., 64 PP`). Der **Fehlercode**-Sensor
dekodiert das automatisch und zeigt **Anzeige-Code + Klartext** als Attribute.
Volle Tabelle: [`docs/fault-codes.md`](docs/fault-codes.md).

## PV-Überschuss — Betriebsmodi

> **Voraussetzung – externe Leistungsmessung (W):** Die Modbus-Schnittstelle liefert
> nur kumulative **kWh**-Register, **keine Momentanleistung**. Der Coordinator-Modus
> braucht daher einen externen **Watt**-Sensor: den **PV-Überschuss-Sensor**
> (`sensor.pv_uberschuss_watt`, roh, kappt bei 0). Ohne ihn bleibt der Coordinator inaktiv.

> **⚠️ Zieltemperaturen: Registergrenze ≠ Gerätegrenze.** Das Hersteller-Datenblatt der
> M7-Reihe nennt beides getrennt: **Einstellbereich *mit Heizstab* 35–75 °C** gegenüber
> **max. Temperaturausgabe *nur Wärmepumpe* 65 °C**. Der Bereich 65–75 °C ist also nur mit
> dem **1500-W-Heizstab** (COP ≈ 1) erreichbar. Die Integration setzt das um: **Normal**
> und **Erhöht** sind auf **65 °C** begrenzt (Verdichter allein), nur die
> **Boost-Zieltemperatur** darf bis **75 °C** (mit Heizstab) — allerdings nur noch im
> **Executor**-Programm „Boost"; im Coordinator-Modus ist Boost eine reine Leistungssenke
> ohne eigene Zieltemperatur und nutzt dieselbe Zieltemperatur wie Erhöht (≤ 65 °C).
> Empfohlen: **50 / 60 / 75 °C**. Belege, Feldmessungen und Hinweise zum
> Legionellen-Schutz: [`docs/geraete-grenzen.md`](docs/geraete-grenzen.md).

Statt eines Bool-Hakens gibt es ein **Dropdown „PV-Modus"** (Setup-Schritt 3 oder
„Konfigurieren"). Es regelt immer nur **ein** Gehirn — kein Doppelregler:

| Modus | Wer entscheidet | Was die Integration tut |
|---|---|---|
| **Aus** | niemand (nur Geräte-ECO/manuell) | nichts; nur die rohen Entitäten + 38-°C-Guard |
| **Coordinator** | die Integration | regelt selbst nach Überschuss + Morgen-Start |
| **Executor** | externes HEMS (z. B. evcc) | regelt nicht selbst; stellt das Programm-Select bereit, das HEMS triggert es |

Die **Stell-Entitäten** (`number.haier_hwhp_set_temp`, `select.haier_hwhp_mode`,
Boost-Switch) bleiben in jedem Modus beschreibbar. Der **38-°C-Guard** ist ein eigener,
separater Haken und bleibt als lokales WW-Sicherheitsnetz aktiv.

### Coordinator (Integration regelt selbst)
Nach **rohem** Überschuss, in **zwei aufeinander abgestimmten Schichten** — bewusst so
gebaut, dass die Wärmepumpe nicht **taktet** (kurze Nachmittags-Kaltstarts) und dass der
**Verdichter immer Vorrang vor dem Heizstab** hat:

**Schicht 1 — WP-Zyklus, 2-stufig (Normal → Erhöht), auf dem *rohen* Überschuss:**
- **Morgen-Start (fix, 1×/Tag):** zur konfigurierten Uhrzeit (Default 10:00 =
  ECO-Fensterstart), wenn das Wasser noch unter der Normal-Temperatur liegt, Sollwert auf
  **Normal** in **ECO** — eine effiziente Grundladung. Bewusst *nicht* Erhöht/AUTO: der
  Morgen-Start ist der garantierte Tagesstart, keine Überschuss-Reaktion (sonst käme an
  trüben Tagen die volle Ladung aus dem Netz). Die Anhebung auf Erhöht folgt bei
  Überschuss über den Piggyback-Zweig unten — ohne neues Startkontingent.
- **Tages-Kaltstart:** überschussgetrieben, mit **Mindestdefizit** — Wasser liegt
  mindestens `pv_coldstart_delta` (Default 10 K) unter der Erhöht-Zieltemperatur, der voll
  entprellte Überschuss erreicht `pv_coldstart` (Default 600 W), Anti-Takt-Zeit
  (`pv_min_off`) ist erfüllt und das **Tageskontingent** (`pv_max_starts`, Default 3) ist
  noch nicht ausgeschöpft. Das Mindestdefizit verhindert Starts für wenige Grad; das
  Kontingent ist die Notbremse, die eigentliche Taktbremse ist `pv_min_off`.
- **Anheben Normal → Erhöht nur bei laufender WP** (Piggyback) über der **Halte-Schwelle**
  (Default 50 W) — kein zusätzlicher Kaltstart, kein Takten.
- **Mindestlaufzeit** (`pv_min_run`, Default 30 min): ein einmal gestarteter Zyklus wird
  so lange gehalten, unabhängig vom Überschuss — eine durchziehende Wolke darf ihn nicht
  abwürgen. Symmetrisch zu `pv_min_off` (Mindest-Stillstand vor dem nächsten Start).
- **Rückfall auf Normal + ECO, sobald ein Zyklus endet** — auch mitten am Tag, damit der
  Tagesplan hält. Ein erneutes Anheben muss Anti-Takt und Tageskontingent erneut passieren.
- **Keine separate Nachtabsenkung:** Der Rückfall auf Normal+ECO ist bereits das
  Nachtverhalten. Fällt die Temperatur nachts unter Normal, heizt das Gerät regulär nach;
  wird es kritisch, eskaliert die Notheizung (s. u.).

**Schicht 2 — Heizstab/Boost, auf dem *normalisierten* Überschuss ("verfügbar"):**
- Der Überschusssensor ist einspeisungsbasiert (Eigenaufnahme bereits abgezogen) — der
  Heizstab würde beim Einschalten seinen eigenen Messwert senken. Das normalisierte Signal
  `verfügbar = roher Überschuss + (Heizstab an ? Heizstableistung : 0)` macht die Schwelle
  invariant gegen die eigene Schalthandlung.
- **Boost** (WP + Heizstab, Reg 2 Bit 1) heißt, was der Name sagt: **beide gemeinsam**, nur
  bei bereits laufender WP. Boost ist eine **Leistungssenke, keine eigene Temperaturstufe**
  — die Zieltemperatur bleibt die der Erhöht-Stufe (≤ 65 °C).
- **Ein/Aus über eine einzige Schwelle** `pv_high` (Default **1600 W** = Heizstab-Nennwert
  1500 W + 100 W Reserve) auf `verfügbar`: **Ein** entprellt (volle Zeit, schützt gegen
  Sensor-Ausreißer), **Aus sofort** (ein Poll) — asymmetrisch, weil Netzbezug beim Heizstab
  strikt vermieden werden soll.
- **Optionaler Negativpreis-Sensor** als **Gate**, kein Schwellensenker: Ist
  `pv_boost_only_negative_price` gesetzt, feuert Boost nur, wenn der Sensor eine
  Negativpreis-Viertelstunde meldet — er verschiebt die Schwelle selbst nicht.
- Fällt der Überschuss unter die Schwelle: **nur der Heizstab** geht weg; die WP läuft
  unverändert weiter (Schicht 1 unberührt).

ELEC (nur Heizstab, WP steht) ist **keine PV-Eskalation mehr** — dafür gibt es die
Notheizung (`emergency.py`), die bei kritisch niedriger Temperatur wahlweise nach AUTO oder
ELEC eskaliert, unabhängig vom Überschuss.

Den aktuellen Zustand zeigt der Diagnose-Sensor **„PV-Regelung Status"**
(`sensor.haier_hwhp_pv_status`: Aus / Normal / Erhöht / Boost, dazu Manueller Eingriff und
„Laufender Zyklus gehalten", mit Überschuss/Sollwert/WP/Heizstab als Attributen); das
mitgelieferte Dashboard hat dafür eine eigene **PV-Sektion** (Status-Kachel +
Logbuch-Verlauf).

Alle Schwellen, Zieltemperaturen und Zeiten sind im „Konfigurieren"-Dialog editierbar —
und praktisch **alle** davon stehen zusätzlich als eigene Entitäten direkt auf der
Geräteseite (Kategorie *Konfiguration*), dieselbe Quelle wie der Dialog, nur bequemer
erreichbar: **Zieltemperaturen, Überschuss-Schwellen, Tagesplan-Kennzahlen**
(Kaltstart-Schwelle/-Defizit, Tageskontingent, Mindestlaufzeit, Mindest-Stillstand,
Entprellzeit, Heizstab-Nennleistung) als `number.haier_hwhp_pv_*`, sowie
`switch.haier_hwhp_pv_boost_only_negative_price` und
`switch.haier_hwhp_pv_morning_enabled`. Ein Ändern dort löst **keinen** Reload aus und
unterbricht damit auch keinen laufenden Zyklus. Notfall-Nachheizung und
Legionellen-Schutz haben ihre eigenen Entitäten (siehe unten) — unabhängig vom
PV-Modus, auch bei `pv_mode: aus` verfügbar.

### Executor (HEMS-Client, z. B. evcc)
Die Integration regelt **nicht**, sondern stellt eine Auswahl-Entität
`select.haier_hwhp_pv_program` bereit, die ein HEMS (oder der Nutzer) setzt:

| Programm | Wirkung |
|---|---|
| `aus` | Sollwert wird nicht angefasst (manuell/Gerät) |
| `grund` | Sollwert = 50 °C, Modus ECO |
| `ueberschuss` | Sollwert = 65 °C, Modus AUTO (überwindet den ECO-Deadband sofort) |
| `boost` | Sollwert = 75 °C + Boost (WP + Heizstab) |

Das HEMS kann zum Steuern **entweder** die Hoch-Ebene (Programm-Select, empfohlen —
die Integration kapselt Sollwert/Modus/Boost) **oder** die Tief-Ebene
(`number.haier_hwhp_set_temp` direkt) nutzen — nicht mischen. Als Status liest es z. B.
`sensor.haier_hwhp_water_temp`, `binary_sensor.haier_hwhp_status_wp`, die Aufnahme
(Shelly) und `sensor.haier_hwhp_set_temp`.

**Effizienz-Strategie (Empfehlung fürs HEMS):** möglichst **ein tiefer Zyklus/Tag** bei
gutem Überschuss (bankt Solarwärme, überbrückt 1–2 Tage → wenige, lange Zyklen statt
vieler kurzer, besser für COP + Lebensdauer); **Kurztakten vermeiden** (Programmwechsel
entprellen, Mindest-Stillstand einhalten); **AUTO nur, wenn nötig** (sonst ECO);
**Boost/Heizstab nur bei wirklich hohem Überschuss**; **38-°C-Guard an lassen**.

evcc kennt die WP nicht nativ → Brücke über HA: *evcc-Entscheidung → MQTT/HA →
Programm-Select/Sollwert*, **nicht** gleichzeitig direkt per Modbus schreiben (kein
zweiter Bus-Master). Beispiel-Automation siehe [`docs/pv-executor-evcc.md`](docs/pv-executor-evcc.md).

## Notfall-Nachheizung & Legionellen-Schutz
Beide sind optional, unabhängig vom PV-Modus und je über einen eigenen Switch aktivierbar
(`switch.haier_hwhp_emergency_enabled` / `switch.haier_hwhp_legionella_enabled`).

**Notfall-Nachheizung:** ECO heizt nur in Zeitfenstern, die Modbus nicht liefert – wird
tagsüber viel Wasser gezogen, kann es vor dem nächsten Fenster ausgehen. Fällt die
Wassertemperatur unter `number.haier_hwhp_emergency_critical` (Standard 38 °C), schaltet
die Integration vorübergehend von ECO auf **AUTO** (WP-Vorrang) oder **ELEC** (nur
Heizstab, schnellste Aufheizung) – wählbar über `select.haier_hwhp_emergency_mode`. Zurück
auf ECO, sobald `number.haier_hwhp_emergency_recover` erreicht ist (mindestens der
aktuelle Sollwert, damit die Rückschaltung nicht in die ECO-Totzone fällt).

**Legionellen-Schutz:** Watchdog-Prinzip statt gelernter Duschgewohnheiten – überwacht nur,
wie lange die letzte vollständige Durchheizung her ist. Wird `number.haier_hwhp_legionella_interval_days`
(Standard 7 Tage) überschritten, erzwingt die Integration einen Desinfektionslauf auf
`number.haier_hwhp_legionella_target` (Standard 65 °C), bevorzugt im konfigurierten
Zeitfenster (`time.haier_hwhp_legionella_window_start`/`_window_end`, Standard 10–18 Uhr)
zunächst in ECO, bei Bedarf eskalierend auf AUTO. Als erfolgreich gilt der Lauf erst, wenn
die Bodentemperatur (`number.haier_hwhp_legionella_bottom_min`) für
`number.haier_hwhp_legionella_hold_min` gehalten wurde. Wird der Speicher aus anderem
Grund ohnehin voll durchgeheizt (z. B. PV-Boost), zählt das als Desinfektion – der Timer
setzt sich zurück, ein Extra-Lauf entfällt. **Verbrühungsrisiko:** bei 65 °C einen
thermostatischen Mischer verwenden.

Rangfolge bei gleichzeitigem Bedarf: Für den **Sollwert** (Reg 6) schreibt nur, wer ihn
besitzt – Legionellen-Schutz vor PV-Regelung, die Notfall-Nachheizung rührt den Sollwert
nicht an. Für den **Modus** (Reg 1) gilt `Legionellen-Schutz > Notfall-Nachheizung >
PV-Regelung`: Die Notfall-Nachheizung wird zwar je Poll zuletzt ausgewertet, hat damit
aber das letzte Wort – kritische Wassertemperatur schlägt PV-Optimierung, bewusst so.

## Dashboard
Beim Setup wird **einmalig** ein **editierbares Storage-Dashboard** „Haier BWWP"
(`/haier-hwhp`) angelegt – per Drag&Drop frei anpassbar, Änderungen bleiben bei
Updates erhalten. Abschnitte: Steuerung, Temperaturen, Status, Energie & COP sowie
Diagramme (Energie pro Monat/Tag, Temperaturen 7 Tage, JAZ-Vergleich). Benötigte
Karten (ApexCharts, card-mod) werden bei Bedarf via HACS nachgezogen.

## Entity-IDs & Verbindung
Alle Entitäten werden auf **`<domain>.haier_hwhp_<key>`** standardisiert. Ein
Modbus-Grundtest je Zyklus unterscheidet Konverter- vs. Geräte-Störung; kurze
Aussetzer halten die letzten Werte bis zu **5 Minuten** (kein Flattern).
Beim kurzen Standard-Abfrageintervall (5 s) wächst die Recorder-Datenbank spürbar —
Vorlage für sinnvolle Ausschlüsse: [`docs/recorder-exclude.yaml`](docs/recorder-exclude.yaml).

## Register, Änderungen & Lizenz
Registerkarte & Herleitung: [`docs/register-map.md`](docs/register-map.md)
(Quelle: Hersteller-Doku „MODBUS Einstellung"). Änderungen je Version:
[`CHANGELOG.md`](CHANGELOG.md). Lizenz: [MIT](LICENSE).

---

## 🇬🇧 English

Local Home Assistant integration for the Haier heat-pump water heater of the
**M7 family** (HP160/HP200/HP260 M7, R290) over **Modbus-TCP** – with **write
access**, energy/COP evaluation and a bundled, editable dashboard. Display name
depends on the system language: **“Haier HWHP”** (English), **“Haier BWWP”** (German).

Fully **local** over Modbus – no hOn cloud account required. Versus the cloud, the
local path offers write access, direct access to the energy registers and runs
**without any internet/cloud dependency**.

### ⚠️ Important: does your unit even have Modbus?
**Not every** unit in this series has the Modbus interface – unofficially it is only
fitted from **production date ~April 2025**. Check the **device/service menu** or the
**manual** for a **Modbus / Slave-ID configuration** item; if present, your unit
supports Modbus (and that's where the **Slave ID**, default `1`, is set).

**Required hardware:**
- Native interface is **Modbus RTU over RS485** (9600 baud, 8N1).
- You need a **Modbus-RTU→TCP converter (gateway)** on the network; Home Assistant
  connects to **its IP on port 502** (not to the heat pump directly).
- The **RS485 cable** from the heat pump (terminals A/B, possibly GND) to the
  converter usually has to be **made yourself**. See the manual for the exact
  terminal layout and this community thread for practical notes:
  [haustechnikdialog.de](https://www.haustechnikdialog.de/Forum/t/285616/Brauchwasserwaermepumpe-Haier-R290).
- Writable registers only accept FC `0x10` (the integration handles this).

### Features
Setup wizard (connection + model → COP → optional PV surplus), bilingual names,
control (setpoint, mode AUTO/ECO/ELEC/VAC, switches), a combined **current source**
display with dynamic icon, temperature/energy sensors, **fault code with plain text**,
calculated **COP/JAZ** with selectable sources, Modbus link diagnostics, built-in
**PV surplus control**, an optional **emergency reheat** (temporarily switches to
AUTO/ELEC at critically low water temperature, independent of the ECO window) and
**legionella protection** (periodic thermal disinfection, watchdog-style, verified via
the tank-bottom temperature — see below), and an **editable storage dashboard**.

### COP / JAZ – system vs. device
The reported COP/JAZ is a **system COP**: with an external meter (Shelly) it includes
**standby, control electronics and the fan** – so it is **noticeably lower** than the
**device's internal** value, which only counts **operating** consumption (no standby/
aux loads), is rounded to whole kWh and reads **far too low**. **Use an external
electricity meter for a meaningful seasonal performance factor.** See
[`docs/register-map.md`](docs/register-map.md).

### Reset energy statistics
On a one-off spike, the service **`haier_modbus.reset_energy_statistics`** clears the
long-term statistics of the total counters (heat + electricity) and rebuilds them
cleanly. This affects **both** counters – their previous daily/monthly history is lost.

### Fault codes
Register 18 returns a number mapped group-wise to the display codes
(`1–15 E.., 16–31 L.., 32–47 F.., 48–63 P.., 64 PP`). The fault sensor decodes it and
exposes **code + description** attributes. Full table:
[`docs/fault-codes.md`](docs/fault-codes.md).

### PV surplus — operating modes
> **Prerequisite – external power (W) metering:** the Modbus interface only exposes
> cumulative **kWh** registers, **not instantaneous power**. The Coordinator mode therefore
> needs an external **watt** sensor: the **PV-surplus sensor** (`sensor.pv_uberschuss_watt`,
> raw, clips at 0). Without it the Coordinator stays inactive.

> **⚠️ Target temperatures: register limit ≠ device limit.** The manufacturer's M7 data
> sheet lists both separately: **setting range *with heater* 35–75 °C** vs. **max.
> temperature output *heat pump only* 65 °C**. The 65–75 °C band is therefore only
> reachable with the **1500 W electric heater** (COP ≈ 1). The integration enforces this:
> **normal** and **elevated** are capped at **65 °C** (compressor alone), only the **boost
> target** may go up to **75 °C** (with the heater) — but only for the **Executor**
> program "boost"; in Coordinator mode Boost is a pure power sink with no target
> temperature of its own and uses the same target as elevated (≤ 65 °C). Recommended:
> **50 / 60 / 75 °C**. Evidence, field measurements and legionella-protection notes:
> [`docs/geraete-grenzen.md`](docs/geraete-grenzen.md).

Instead of a checkbox there is a **"PV mode" dropdown** (setup step 3 / *Configure*).
Only **one** brain ever regulates — no double controller:

| Mode | Who decides | What the integration does |
|---|---|---|
| **Off** | nobody (device ECO/manual) | nothing; only the raw entities + 38 °C guard |
| **Coordinator** | the integration | regulates from surplus + a fixed morning start |
| **Executor** | external HEMS (e.g. evcc) | does not regulate; provides the program select, the HEMS triggers it |

The **control entities** (`number.haier_hwhp_set_temp`, `select.haier_hwhp_mode`, boost
switch) stay writable in every mode. The **38 °C guard** is a separate option and stays
active as a local hot-water safety net.

**Coordinator** regulates from the surplus in **two coordinated layers**, deliberately
built so the heat pump does not **short-cycle** and so the **compressor always takes
precedence over the electric heater**:

*Layer 1 — heat-pump cycle, 2 tiers (normal → elevated), on the **raw** surplus:*
- **Fixed once-a-day morning start:** at the configured time (default 10:00 = ECO window
  start), if the water is still below normal, setpoint goes to **normal** in **ECO** — an
  efficient base charge. Deliberately *not* elevated/AUTO: the morning start is the
  guaranteed daily start, not a surplus reaction (otherwise a cloudy day would pull the
  full charge from the grid). The rise to elevated follows on surplus via the piggyback
  branch below — without spending a start allowance.
- **Daily cold start:** surplus-driven, with a **minimum deficit** — the water sits at
  least `pv_coldstart_delta` (default 10 K) below the elevated target, the fully debounced
  surplus reaches `pv_coldstart` (default 600 W), the anti-cycling time (`pv_min_off`) is
  satisfied, and the **daily start allowance** (`pv_max_starts`, default 3) isn't spent
  yet. The minimum deficit blocks starts for a few degrees; the allowance is the backstop,
  the actual anti-cycling guard is `pv_min_off`.
- **Raising normal → elevated only while the pump is already running** (piggyback), above
  the **hold threshold** (default 50 W) — no extra cold start, no cycling.
- **Minimum run time** (`pv_min_run`, default 30 min): once a cycle starts it is held for
  at least this long regardless of surplus — a passing cloud must not abort it. Symmetric
  to `pv_min_off` (minimum standstill before the next start).
- **Falls back to normal + ECO as soon as a cycle ends** — even mid-day, to keep the daily
  plan intact. Raising it again must pass the anti-cycling guard and the daily allowance.
- **No separate night setback:** the fallback to normal+ECO above already is the night
  behaviour. If the temperature drops below normal overnight the device reheats normally;
  if it gets critical, the emergency reheat escalates (see below).

*Layer 2 — electric heater/boost, on the **normalized** surplus ("available"):*
- The surplus sensor is feed-in based (self-consumption already subtracted) — the heater
  would lower its own reading the moment it switches on. The normalized signal
  `available = raw surplus + (heater on ? heater power : 0)` makes the threshold invariant
  against its own switching action.
- **Boost** (pump + heater, Reg 2 bit 1) means what the name says — **both together**,
  only while the pump is already running. Boost is a **power sink, not its own temperature
  tier** — the target stays the elevated target (≤ 65 °C).
- **A single on/off threshold** `pv_high` (default **1600 W** = heater nominal power
  1500 W + 100 W margin) on `available`: **on** is debounced (the full time, to guard
  against sensor outliers), **off is immediate** (one poll) — asymmetric, because grid
  draw for the heater must be strictly avoided.
- **Optional negative-price sensor as a gate**, not a threshold-lowerer: if
  `pv_boost_only_negative_price` is set, Boost only fires while the sensor reports a
  negative-price quarter-hour — it does not shift the threshold itself.
- If the surplus drops below the threshold: **only the heater** drops out; the pump keeps
  running unchanged (layer 1 unaffected).

ELEC (heater only, pump off) is **no longer part of the PV escalation** — that's now the
emergency reheat (`emergency.py`), which escalates to AUTO or ELEC on critically low
temperature, independent of surplus.

The diagnostic sensor **“PV control status”** (`sensor.haier_hwhp_pv_status`) shows the
live state (off / base / normal / boost, plus manual override and “active cycle held”,
with surplus/setpoint/pump/heater attributes); the bundled dashboard has a dedicated PV
section for it. All thresholds, target temps and timings are editable in the Configure
dialog — and virtually **all** of them are additionally exposed as entities on the
device page (*config* category), same single source of truth as the dialog, just
easier to reach: **target temperatures, surplus thresholds, daily-plan figures**
(cold-start threshold/deficit, daily start allowance, minimum run time, minimum
off-time, debounce time, heater rated power) as `number.haier_hwhp_pv_*`, plus
`switch.haier_hwhp_pv_boost_only_negative_price` and
`switch.haier_hwhp_pv_morning_enabled`. Changing them there triggers **no** reload, so
a running cycle is not disturbed. Emergency reheat and legionella protection have
their own entities (see below) — independent of PV mode, available even at
`pv_mode: off`.

**Executor** does not regulate; it exposes `select.haier_hwhp_pv_program`
(`aus`/`grund`/`ueberschuss`/`boost`) that an external HEMS (or you) sets — the
integration translates the program into setpoint/mode/boost. A HEMS controls **either**
the high level (program select, recommended) **or** the low level
(`number.haier_hwhp_set_temp` directly), not both. For efficiency: aim for **one deep
cycle per day** at good surplus (fewer, longer cycles → better COP & lifetime), **avoid
short-cycling** (debounce program changes, keep a minimum off-time), use **AUTO only when
needed**, **Boost/heater only at really high surplus**, and **keep the 38 °C guard on**.
evcc doesn't know the heat pump natively → bridge via HA (*evcc decision → MQTT/HA →
program select/setpoint*), never write Modbus directly in parallel (avoid a second bus
master). Example automation: [`docs/pv-executor-evcc.md`](docs/pv-executor-evcc.md).

### Emergency reheat & legionella protection
Both are optional, independent of PV mode, and each toggled via its own switch
(`switch.haier_hwhp_emergency_enabled` / `switch.haier_hwhp_legionella_enabled`).

**Emergency reheat:** ECO only heats within time windows that Modbus doesn't expose —
if a lot of water is drawn during the day, it can run out before the next window. If the
water temperature drops below `number.haier_hwhp_emergency_critical` (default 38 °C),
the integration temporarily switches ECO to **AUTO** (heat-pump priority) or **ELEC**
(heater only, fastest reheat) — selectable via `select.haier_hwhp_emergency_mode`. Back
to ECO once `number.haier_hwhp_emergency_recover` is reached (never below the current
setpoint, so the switch-back doesn't fall into the ECO dead zone).

**Legionella protection:** watchdog-style rather than learned shower habits — it only
tracks how long ago the last full heat-up was. Once
`number.haier_hwhp_legionella_interval_days` (default 7 days) is exceeded, the
integration forces a disinfection run to `number.haier_hwhp_legionella_target` (default
65 °C), preferably within the configured window
(`time.haier_hwhp_legionella_window_start`/`_window_end`, default 10:00–18:00),
first in ECO and escalating to AUTO if needed. The run only counts as successful once
the tank-bottom temperature (`number.haier_hwhp_legionella_bottom_min`) has held for
`number.haier_hwhp_legionella_hold_min`. If the tank gets fully heated anyway for some
other reason (e.g. PV boost), that counts as disinfection too — the timer resets, no
extra run happens. **Scald risk:** use a thermostatic mixing valve at 65 °C.

Precedence when both apply: for the **setpoint** (Reg 6), only the owner writes —
legionella protection before PV control, emergency reheat never touches the setpoint.
For the **mode** (Reg 1): `legionella protection > emergency reheat > PV control` —
emergency reheat is evaluated last each poll, so it gets the final word; critical water
temperature deliberately beats PV optimization.

### Installation (HACS)
HACS → custom repository (category *Integration*) → download → restart → add the
integration → enter the **converter's IP**, port `502`, slave `1`, interval, model.
Everything is changeable later under *Configure*. License: [MIT](LICENSE).
