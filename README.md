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
Nach **rohem** Überschuss, in **zwei unabhängigen Schichten** — bewusst so gebaut, dass
die Wärmepumpe nicht **taktet** (kurze Nachmittags-Kaltstarts):

**Schicht 1 — WP-Zyklus (Grund ↔ Normal):**
- **Morgen-Start (fix):** einmal/Tag zur konfigurierten Uhrzeit (Default 10:00 =
  ECO-Fensterstart) ein Kick auf Normal, wenn das Wasser noch unter der Grundtemperatur
  liegt — der **einzige Kaltstart** des Tages.
- **Anheben auf Normal nur bei laufender WP** (Piggyback) über der **Halte-Schwelle**
  (Default 50 W) → kein Tages-Kaltstart, kein Takten.
- **Absenken** auf Grund, wenn der Überschuss für die **Entprellzeit** (5 min) unter die
  Halte-Schwelle fällt **und** der Heizstab aus ist.

**Schicht 2 — Heizstab (ad-hoc Zusatz, stoppt nie die WP):** ab der **Hoch-Schwelle**
(Default 1550 W = Heizstab ~1500 W + Puffer) auf die Hochtemperatur plus:
- **Boost** (WP + Heizstab) **nur bei laufender** WP,
- **Heizstab (ELEC)** **nur bei stehender** WP (ELEC würde die WP sonst stoppen) — dumpt
  sofort, z. B. um nach dem Tageszyklus Überschuss zu verheizen; danach zurück auf ECO +
  Grundtemperatur.

Fällt der Überschuss weg, geht **nur der Heizstab** weg (Sollwert Hoch→Normal/Grund); die
WP läuft unverändert weiter. Solange der Heizstab an ist, hält Schicht 1 die Normalstufe.

Den aktuellen Zustand zeigt der Diagnose-Sensor **„PV-Regelung Status"**
(`sensor.haier_hwhp_pv_status`: Aus / Grund / Normal / Hoch + Boost / Hoch + ELEC, mit
Überschuss/Sollwert/WP/Heizstab als Attributen); das mitgelieferte Dashboard hat dafür
eine eigene **PV-Sektion** (Status-Kachel + Logbuch-Verlauf).

Alle Schwellen, Zieltemperaturen und Zeiten sind im „Konfigurieren"-Dialog editierbar.

### Executor (HEMS-Client, z. B. evcc)
Die Integration regelt **nicht**, sondern stellt eine Auswahl-Entität
`select.haier_hwhp_pv_program` bereit, die ein HEMS (oder der Nutzer) setzt:

| Programm | Wirkung |
|---|---|
| `aus` | Sollwert wird nicht angefasst (manuell/Gerät) |
| `grund` | Sollwert = Grundtemp (50), Modus ECO |
| `ueberschuss` | Sollwert = Normaltemp (65), Modus AUTO (überwindet den ECO-Deadband sofort) |
| `boost` | Sollwert = Hochtemp (75) + Boost (WP + Heizstab) |

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
zweiter Bus-Master). Beispiel-Automation siehe [`docs/pv-rework-plan.md`](docs/pv-rework-plan.md), Kap. 11.

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
**PV surplus control**, and an **editable storage dashboard**.

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

**Coordinator** controls the setpoint in three tiers (50/65/75) from the **raw** surplus,
made oscillation-free by a once-a-day **morning start** (kick to 65 if water is still
below base), **hold/lower** with debounce (stay at 65 above the hold threshold, drop to
50 once surplus stays below it), an optional **daytime re-raise** (back to 65 above the
re-raise threshold, with anti-short-cycle), and **75 + escalation** (Boost / ELEC heater)
at very high surplus — which also fires **when the heat pump is off**: Boost starts
pump+heater (anti-short-cycle protected), ELEC dumps into the heater immediately (no
compressor cycle), e.g. to burn surplus after the daily cycle. All thresholds, target
temps and timings are editable in the Configure dialog.

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
master). Example automation: [`docs/pv-rework-plan.md`](docs/pv-rework-plan.md), §11.

### Installation (HACS)
HACS → custom repository (category *Integration*) → download → restart → add the
integration → enter the **converter's IP**, port `502`, slave `1`, interval, model.
Everything is changeable later under *Configure*. License: [MIT](LICENSE).
