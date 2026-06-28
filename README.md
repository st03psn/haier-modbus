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
- **PV-Überschuss-Steuerung** eingebaut (optional): verfügbar-Modell + Hysterese + Anti-Takt.
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

## PV-Überschuss-Steuerung

> **Voraussetzung – externe Leistungsmessung (W):** Die Modbus-Schnittstelle liefert
> nur kumulative **kWh**-Register, **keine Momentanleistung**. Die PV-Überschuss-Steuerung
> braucht daher externe **Watt**-Sensoren: den **PV-Überschuss-Sensor** (Pflicht) und –
> für das pendelfreie „verfügbar"-Modell – den **BWWP-Leistungssensor** (z. B. ein Shelly
> an der Wärmepumpe). Ohne BWWP-Sensor regelt die Funktion nur auf den rohen Überschuss
> (Pendel-Gefahr) und ist dann nur eingeschränkt sinnvoll. Ohne diese externen Sensoren
> ergibt das Feature **keinen Sinn** – die Modbus-Integration allein kennt die nötigen
> Watt-Werte nicht.

Im Setup (Schritt 3) oder unter „Konfigurieren" aktivieren: **PV-Überschuss-Sensor**
und **BWWP-Leistungssensor** wählen. Die Integration regelt die Solltemperatur
dreistufig nach **verfügbarem Solarstrom** (`PV-Überschuss + aktuelle WP-Aufnahme`).
Diese Summe springt nicht beim Ein-/Ausschalten der WP → **kein Pendeln**. Dazu:

- **Hysterese** – Hoch- und Rückschalten getrennt (Rückschalt-Schwelle = Einschalt-Schwelle − Hysterese).
- **Anti-Takt-Schutz** – ein neuer Verdichter-Zyklus startet erst nach einem
  Mindest-Stillstand; läuft die WP bereits, wird die Stufe verlängert statt neu
  gestartet (Piggyback).
- Optional bei hohem Überschuss zusätzlich **Boost** und/oder **Heizstab (ELEC)**.

Alle Schwellen, Zieltemperaturen, Hysterese und Zeiten sind im „Konfigurieren"-Dialog
**jederzeit editierbar**; der Haken **„PV-Überschuss-Steuerung aktiv"** schaltet die
Steuerung ein/aus. Ohne PV-Sensor bleibt die Funktion inaktiv.

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

### PV surplus
> **Prerequisite – external power (W) metering:** the Modbus interface only exposes
> cumulative **kWh** registers, **not instantaneous power**. PV-surplus control therefore
> needs external **watt** sensors: the **PV-surplus sensor** (required) and — for the
> oscillation-free "available solar" model — the **heat-pump power sensor** (e.g. a Shelly
> on the heat pump). Without the heat-pump sensor it falls back to the raw surplus
> (oscillation risk). Without these external sensors the feature makes **little sense** —
> the Modbus integration alone does not know the required watt values.

Enable in the setup wizard / *Configure*, pick a **PV-surplus sensor** and a
**heat-pump power sensor**. The integration regulates the setpoint in three tiers
based on **available solar** (`PV surplus + current HP draw`) — switch-invariant,
so no oscillation — with **hysteresis** (separate up/down thresholds) and
**anti-short-cycle** protection (a new cycle starts only after a minimum off-time;
if the pump already runs, the tier is extended — piggyback). Optional Boost / ELEC
heater escalation on high surplus. All thresholds, target temps, hysteresis and
timings are **editable any time** in the Configure dialog; the **enable checkbox**
turns the control on/off.

### Installation (HACS)
HACS → custom repository (category *Integration*) → download → restart → add the
integration → enter the **converter's IP**, port `502`, slave `1`, interval, model.
Everything is changeable later under *Configure*. License: [MIT](LICENSE).
