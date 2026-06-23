# Haier Brauchwasserwärmepumpe / BWWP (Modbus)

Lokale Home-Assistant-Integration für die Haier Brauchwasserwärmepumpe (**BWWP**,
engl. DHWHP) der **M7-Familie** (HP160/HP200/HP260 M7) über **Modbus-TCP** – ohne
hOn-Cloud, mit **Schreibzugriff** und **gerätegemessener Energie-/COP-Auswertung**.

> Standalone-Integration, unabhängig von `hOn-unified`. Die BWWP ist das eine Gerät
> mit lokalem Interface – hier ist der lokale Pfad dem Cloud-Pfad auf jeder Achse
> überlegen (Schreibzugriff, Energieregister, keine Cloud-Abhängigkeit).

## Funktionen

- **Einrichtungs-Assistent** (Config-Flow): Verbindung (Host, Port, Slave-ID,
  Intervall) + **Modell**, danach direkt der **COP-Assistent**
- **Zweisprachig** (Deutsch / Englisch) – folgt der HA-Nutzersprache
- **Ein Gerät** mit allen Entitäten gruppiert; `water_heater`-Kachel als zentrale Bedienung
- **Steuerung (RW):** Solltemperatur (Number), Modus (Select: AUTO/ECO/ELEC/VAC),
  Schalter Aktiv/Boost/Leise/Sterilisation (Bits im Funktionsregister)
- **Status:** Wärmepumpe / Heizstab aktiv, **Aktuelle Quelle** (konsolidiert),
  Verbindung, **Modbus-Status**; **Solar / Kessel** (externe Quellen via Speicher-
  Heizregister) sind standardmäßig **deaktiviert** und werden **automatisch
  freigeschaltet, sobald die Quelle erstmals aktiv** ist (kein Capability-Register
  am Gerät – ein gesetztes Bit beweist die Existenz)
- **Sensoren:** Wasser-, Ziel-, Tank-oben/-unten-, Umgebungstemperatur, Warmwasser %,
  Fehlercode, Modus-Text
- **Energie & COP:** WP-Strom, Heizstab-Strom, Wärmemenge (gerätegemessen, dieses Jahr)
  und ein **berechneter COP** – mit **frei wählbaren Energiequellen** (Modbus-intern
  oder externer Sensor wie Shelly)
- **PV-Überschuss-Blueprint** für die Solltemperatur-Steuerung
- **Ein Block-Read** (Register 1–90) je Intervall; Schreibzugriff über FC `0x10`

## Installation (HACS)

1. HACS → ⋮ → **Benutzerdefinierte Repositorys** → URL dieses Repos, Kategorie **Integration**
2. „Haier BWWP (Modbus)" herunterladen, HA neu starten
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen** → „Haier" suchen
4. **Schritt 1 – Verbindung:** Host (i. d. R. der **Modbus-RTU→TCP-Konverter**,
   z. B. `192.168.42.112`), Port `502`, Slave `1`, Intervall `5`, Modell
5. **Schritt 2 – COP/Energie:** Quellen wählen
6. **Schritt 3 – PV-Überschuss (optional):** Überschuss-Sensor + Schwellen

Alles (inkl. **Host/Port/Slave des Modbus-Konverters**) ist später jederzeit unter
**Geräte & Dienste → Haier … → Konfigurieren** änderbar.

Alternativ rein lokal: Ordner `custom_components/haier_modbus/` nach
`<config>/custom_components/` kopieren und HA neu starten.

## COP konfigurieren

Im Einrichtungs-Assistenten oder später unter **Geräte & Dienste → Haier … → Konfigurieren**:

- **Wärmequelle:** Modbus (Register 90, gerätegemessen) oder externer Wärmemengenzähler
- **Stromquelle:** Modbus (Register 42 + 66) oder externer Zähler (z. B. `sensor.shelly_…_energy`)
- **Skalierung** der kWh-Register (`×1` / `×0.1`), siehe `docs/register-map.md`

> **Wichtig:** Das Wärmeregister (累计制热量) existiert laut Doku. Ob der Geräte-COP
> belastbar ist, hängt davon ab, ob Register 90 die Wärme *misst* oder nur aus dem
> Strom *zurückrechnet*. Vor Nutzung verifizieren – siehe `docs/register-map.md`.

### COP/JAZ & aligned windows

Geräteinterne „dieses Jahr"-Register von Strom und Wärme resetten zu
*unterschiedlichen* Zeitpunkten – ihr Verhältnis wäre wertlos. Die Integration
löst das mit einem internen, kalender-ausgerichteten Akkumulator (utility_meter-
Logik): Strom und Wärme werden in **gemeinsame Monats- und Jahres-Fenster**
gezählt, Quell-Resets werden abgefangen. Daraus:

- **`COP (Monat)`** – monatlicher Arbeitszahl-Wert
- **`JAZ (Jahr)`** – Jahresarbeitszahl
- **`Wärme erzeugt (gesamt)`** / **`Stromverbrauch (gesamt)`** – monotone
  `total_increasing`-Energiesensoren für **Verbrauchs-/Erzeugungskurven**
  (History/Statistik automatisch; im **Energie-Dashboard** einmalig hinzufügen).
  Beim ersten Start auf den Zeitraum **„seit dem ersten Wärmewert"** vorbefüllt
  (Wärme = Geräte-Jahreswert, Strom = Verbrauch ab dem ersten Monat mit Wärme),
  danach reset-fest weiterzählend – so sind Wärme und Strom direkt vergleichbar.

**`COP (seit Bezugsdatum)`:** Liefert **sofort** einen Wert, ohne auf eine volle
Periode zu warten. Das **Bezugsdatum wird automatisch ermittelt** – der erste
Monat des laufenden Jahres mit Wärme > 0 (aus den Geräte-Monatswerten, Reg 74–85);
ein manuelles Datum im COP-Setup überschreibt das nur bei Bedarf. Dann gilt:
Wärme = aktueller Geräte-Zähler (seit diesem Datum), Strom = Verbrauch seit
demselben Datum (aus der Statistik der gewählten Stromquelle). Beide decken
denselben Zeitraum ab – ohne dass eine Wärme-Historie nötig ist. Attribute:
`reference_date` und `reference_auto`. Ein gesetztes Bezugsdatum richtet auch das
**Monats-/Jahres-/Gesamt-Seeding** danach aus (Strom erst ab dem Datum); eine
Änderung des Datums seedet einmalig neu.

**Jahres-/Monatsvergleich (JAZ/COP):** Beim Jahres-/Monatswechsel wird der fertige
Wert dauerhaft archiviert: Attribut `jaz_per_year` am **`JAZ (Jahr)`**-Sensor und
`cop_per_month` am **`COP (Monat)`**-Sensor (je `{heat, elec, cop}`), plus Sensor
**`JAZ (Vorjahr)`**. Fertige Vergleichskarte (ApexCharts):
[`docs/lovelace-jaz-card.yaml`](docs/lovelace-jaz-card.yaml). Wächst ab Mess-Start.

> Die benötigte **ApexCharts-Card wird automatisch über HACS nachinstalliert**
> (sofern HACS vorhanden). Klappt das nicht, erscheint ein Reparatur-Hinweis mit
> Installationslink. Danach Browser neu laden (Strg+Shift+R).

**Rückwirkendes Seeding:** Beim ersten Start werden Monats- und Jahres-Fenster
einmalig aus der HA-Langzeitstatistik vorbefüllt (reset-bereinigte `sum`), damit
COP/JAZ nicht erst ab Inbetriebnahme zählen. Wärme- und Stromquelle werden dabei
auf den **gemeinsamen frühesten Datenzeitpunkt** ausgerichtet (also „ab dem auch
Wärme verfügbar war"), damit beide denselben Zeitraum abdecken. Best-effort: ohne
verwertbare Statistik wird übersprungen und ab dann vorwärts gezählt.

## PV-Überschuss-Steuerung

**Eingebaut (empfohlen):** im Setup-Assistenten (Schritt 3) oder unter
„Konfigurieren" aktivieren. Du wählst nur den **PV-Überschuss-Sensor (W)** und
optional die Schwellen/Zieltemperaturen; die Integration setzt die Solltemperatur
dreistufig (hoch/normal/Grund) mit Entprellzeit und regelt nur, wenn nötig.
Optional bei **hohem Überschuss**: zusätzlich **Boost** aktivieren und/oder den
**Heizstab** (Modus ELEC) zuschalten, um den Überschuss maximal zu nutzen
(Boost/Modus werden beim Absinken wieder zurückgenommen).

**Alternativ als Blueprint:**
[`blueprints/automation/haier_modbus/pv_surplus.yaml`](blueprints/automation/haier_modbus/pv_surplus.yaml)
(Einstellungen → Automationen & Szenen → Blueprints → **Blueprint importieren**),
falls du die Logik lieber als Automation mit eigenen Anpassungen/Notifications führst.

## Entity-IDs

Beim Setup werden alle Entitäten auf ein einheitliches, internationales Schema
**`<domain>.hwhp_<key>`** standardisiert (Bestand wird einmalig migriert), z. B.
`sensor.hwhp_water_temp`, `number.hwhp_set_temp`, `water_heater.hwhp`. Die
**Anzeigenamen** folgen der HA-Systemsprache (Deutsch, sonst Englisch). Verweise
auf zuvor abweichende entity_ids in eigenen Automationen/Karten ggf. anpassen.

## Verbindung & Diagnose

Ein **Modbus-Grundtest** je Zyklus unterscheidet, ob der **Konverter** (TCP)
nicht erreichbar ist oder der Konverter zwar antwortet, aber das **Gerät** (RTU)
stumm bleibt. Ergebnis im diagnostischen Sensor **`Modbus-Status`**
(`ok` / `Konverter nicht erreichbar` / `Gerät antwortet nicht`); der Binärsensor
**`Verbindung`** spiegelt `ok`. Kurze Aussetzer setzen die Entitäten **nicht**
sofort auf „nicht verfügbar" – die letzten Werte werden bis zu **5 Minuten**
gehalten (danach erst „nicht verfügbar"). So flappt nichts bei einzelnen Blips.

## Kalibrierung

Der geräteseitige **Umgebungstemperatur**-Fühler liegt oft daneben. Unter
**Konfigurieren** lässt sich ein additiver **Offset (°C)** setzen, der direkt auf
den Sensor `Umgebungstemperatur` angewandt wird.

## Dashboard

Die Integration liefert ein **fertiges Dashboard** mit und registriert es beim
Setup automatisch in der Seitenleiste (**„Haier BWWP"**, `/haier-bwwp`).
Es wird zur Laufzeit aus den real registrierten Entitäten erzeugt (Auflösung über
`unique_id`), passt also unabhängig von den konkreten entity_ids – Karten zu
(noch) fehlenden Entitäten werden ausgelassen. Abschnitte: Steuerung,
Temperaturen, Status, Energie & COP, Verlauf (ApexCharts). Beim Entfernen der
Integration verschwindet das Dashboard wieder. (Die ApexCharts-Karte wird bei
Bedarf automatisch via HACS nachgezogen.)

## Recorder / Datenbank

Standard-Abfrageintervall ist **5 s**. Damit die Datenbank nicht durch
historienlose Werte wächst, empfiehlt sich ein Recorder-Ausschluss für
flatternde/redundante Entitäten (Verbindung, Modus-Text, Warmwasserstand,
Zieltemperatur). Fertiger Block: [`docs/recorder-exclude.yaml`](docs/recorder-exclude.yaml)
– in die `configuration.yaml` übernehmen und HA neu starten.

## Register & Validierung

Vollständige Registerkarte und COP-Herleitung: [`docs/register-map.md`](docs/register-map.md).
Quelle: offizielle Hersteller-Doku „Haier-Haustechnik.de Brauchwasser-WP MODBUS Einstellung".

## Lizenz

[MIT](LICENSE).
