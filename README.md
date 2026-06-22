# Haier Brauchwasserwärmepumpe (Modbus)

Lokale Home-Assistant-Integration für die Haier Brauchwasserwärmepumpe **HP200M7-F9**
über **Modbus-TCP** – ohne hOn-Cloud, mit **Schreibzugriff** und **gerätegemessener
Energie-/COP-Auswertung**.

> Standalone-Integration, unabhängig von `hOn-unified`. Die BWWP ist das eine Gerät
> mit lokalem Interface – hier ist der lokale Pfad dem Cloud-Pfad auf jeder Achse
> überlegen (Schreibzugriff, Energieregister, keine Cloud-Abhängigkeit).

## Funktionen

- **Einrichtung über die Oberfläche** (Config-Flow): Host, Port, Slave-ID, Intervall
- **Ein Gerät** mit allen Entitäten gruppiert; `water_heater`-Kachel als zentrale Bedienung
- **Steuerung (RW):** Solltemperatur (Number), Modus (Select: AUTO/ECO/ELEC/VAC),
  Schalter Aktiv/Boost/Leise/Sterilisation (Bits im Funktionsregister)
- **Status:** Wärmepumpe / Heizstab / Solar / Kessel aktiv, Verbindung
- **Sensoren:** Wasser-, Ziel-, Tank-oben/-unten-, Umgebungstemperatur, Warmwasser %,
  Fehlercode, Modus-Text
- **Energie & COP:** WP-Strom, Heizstab-Strom, Wärmemenge (gerätegemessen, dieses Jahr)
  und ein **berechneter COP** – mit **frei wählbaren Energiequellen** (Modbus-intern
  oder externer Sensor wie Shelly), alles im Options-Dialog
- **Ein Block-Read** (Register 1–90) je Intervall statt vieler Einzelabfragen

## Installation (HACS)

1. HACS → ⋮ → **Benutzerdefinierte Repositorys** → URL dieses Repos, Kategorie **Integration**
2. „Haier Brauchwasserwärmepumpe (Modbus)" herunterladen, HA neu starten
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen** → „Haier" suchen
4. Host (z. B. `192.168.42.112`), Port `502`, Slave `1`, Intervall `30` eingeben

Alternativ rein lokal: Ordner `custom_components/haier_modbus/` nach
`<config>/custom_components/` kopieren und HA neu starten.

## COP konfigurieren

Unter **Geräte & Dienste → Haier … → Konfigurieren**:

- **Wärmequelle:** Modbus (Register 90, gerätegemessen) oder externer Wärmemengenzähler
- **Stromquelle:** Modbus (Register 42 + 66) oder externer Zähler (z. B. `sensor.shelly_…_energy`)
- **Skalierung** der kWh-Register (`×1` / `×0.1`), siehe `docs/register-map.md`

> **Wichtig:** Ob der Geräte-COP belastbar ist, hängt davon ab, ob Register 90 die
> Wärme *misst* oder nur aus dem Strom *zurückrechnet*. Vor Nutzung verifizieren –
> siehe `docs/register-map.md`.

## Register & Validierung

Vollständige Registerkarte und COP-Herleitung: [`docs/register-map.md`](docs/register-map.md).
Quelle: offizielle Hersteller-Doku „Haier-Haustechnik.de Brauchwasser-WP MODBUS Einstellung".

## Lizenz

[MIT](LICENSE).
