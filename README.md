# Haier Brauchwasserwärmepumpe / BWWP (Modbus)

Lokale Home-Assistant-Integration für die Haier Brauchwasserwärmepumpe (**BWWP**,
engl. DHWHP) der **M7-Familie** (HP160/HP200/HP260 M7) über **Modbus-TCP** – ohne
hOn-Cloud, mit **Schreibzugriff** und **gerätegemessener Energie-/COP-Auswertung**.

> Standalone-Integration, unabhängig von `hOn-unified`. Die BWWP ist das eine Gerät
> mit lokalem Interface – hier ist der lokale Pfad dem Cloud-Pfad auf jeder Achse
> überlegen (Schreibzugriff, Energieregister, keine Cloud-Abhängigkeit).

## Funktionen

- **Einrichtungs-Assistent** (Config-Flow): Verbindung (Host, Port, Slave-ID,
  Intervall) + **Modell/Tankvolumen**, danach direkt der **COP-Assistent**
- **Zweisprachig** (Deutsch / Englisch) – folgt der HA-Nutzersprache
- **Ein Gerät** mit allen Entitäten gruppiert; `water_heater`-Kachel als zentrale Bedienung
- **Steuerung (RW):** Solltemperatur (Number), Modus (Select: AUTO/ECO/ELEC/VAC),
  Schalter Aktiv/Boost/Leise/Sterilisation (Bits im Funktionsregister)
- **Status:** Wärmepumpe / Heizstab / Solar / Kessel aktiv, **Aktuelle Quelle**
  (konsolidiert), Verbindung
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
   z. B. `192.168.42.112`), Port `502`, Slave `1`, Intervall `5`, Modell + Tankvolumen
5. **Schritt 2 – COP/Energie:** Quellen wählen (kann später jederzeit unter
   „Konfigurieren" angepasst werden)

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
  (History/Statistik automatisch; im **Energie-Dashboard** einmalig hinzufügen)

## PV-Überschuss-Automation

Blueprint: [`blueprints/automation/haier_modbus/pv_surplus.yaml`](blueprints/automation/haier_modbus/pv_surplus.yaml).
Setzt die Solltemperatur dreistufig nach PV-Überschuss (hoch/normal/aus). Import:

> Einstellungen → Automationen & Szenen → Blueprints → **Blueprint importieren** →
> URL der Blueprint-Datei (Raw-Link auf GitHub) einfügen.

Benötigt: PV-Überschuss-Sensor (W), die **Solltemperatur**-Number der Integration,
einen Wassertemperatur-Sensor; optional ein `notify`-Dienst.

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
