# Gerätegrenzen der Haier-BWWP-M7-Familie

Wichtig für die Konfiguration der PV-Steuerung und des Legionellen-Schutzes:
**Das Modbus-Register erlaubt mehr, als das Gerät kann.**

## Temperaturgrenzen

Das **Hersteller-Datenblatt** der M7-Reihe führt zwei **getrennte** Temperaturzeilen — genau
die hier entscheidende Unterscheidung:

| Datenblatt-Zeile | Wert |
|---|---|
| Temperatureinstellbereich **mit Heizstab** | **35–75 °C** |
| Max. Temperaturausgabe **nur Wärmepumpe** | **65 °C** |

Ergänzend:

| Größe | Wert |
|---|---|
| Sollwert-Register (Reg 6) | 35–75 °C schreibbar (Hersteller-Modbus-Doku) |
| Integrierter E-Heizstab | **1500 W** – „als Reserve oder zur schnellen Warmwassererzeugung im Boost-Modus"; im **BOOST**-Modus arbeiten WP und Heizstab gleichzeitig |
| Geräteeigene Sterilisation | heizt 1×/Woche auf **75 °C** |
| COP (Herstellerangabe) | 3,27–3,5 |

Gilt laut Datenblatt für **HP200M7-F9 / HP250M7-F9 / HP200M7C-F9 / HP250M7C-F9**.

**Primärquelle (Datenblatt, Spezifikationstabelle):**
[haierhvac.eu – PF_HPWH_M7](https://haierhvac.eu/sites/haierhvac-eu/files/2024-06/20240610_PF_HPWH_M7_ENG.pdf) ·
davon abgeleitete technische Datenblätter: [Hornbach](https://media.hornbach.de/hb/technicaldatasheet/as.162983863.pdf) ·
[Otto](https://d.otto.de/files/ee3ddb74-cdb4-5685-ab13-601c94b63a4e.pdf) ·
Betriebs-/Montageanleitung: [heima24 (PDF)](https://www.heima24.de/shop/images/products/media/betr-ma-hpm200-250-m7c-f9.pdf)

> **Konsequenz:** Der Bereich **65–75 °C** ist laut Datenblatt nur **„mit Heizstab"**
> erreichbar. Ein Sollwert von 70–75 °C ist über Modbus zwar schreibbar, liegt aber
> oberhalb der ausgewiesenen Wärmepumpen-Maximaltemperatur.

## Feldbeobachtung (konsistent mit dem Datenblatt)

Aus vier Monaten Langzeitstatistik einer realen HP200M7-F9:

- **Monats-Maxima der Wassertemperatur: 57 / 64 / 65 °C** — nie darüber.
- Ein vollständiger Zyklus bis **65 °C** lief **rein über den Verdichter**
  (`binary_sensor.*_status_heater` durchgehend `off`) → 65 °C sind ohne Heizstab erreichbar.

> *Einordnung:* Diese Beobachtung ist **konsistent** mit der Datenblattangabe, beweist sie
> aber nicht eigenständig — im beobachteten Zeitraum lag der Sollwert nie über 65 °C, ein
> Versuch oberhalb der Grenze wurde also nie gefahren. Die Grenze selbst steht im Datenblatt
> (Tabelle oben); die Messung zeigt zusätzlich, wie sich die Leistung nach oben hin verhält.
- **Messbarer Kapazitätsabfall zum Ende hin**, im selben Zyklus:

  | Bereich | Aufheizrate |
  |---|---|
  | 53 → 59 °C | ≈ **6,0 K/h** |
  | 60 → 65 °C | ≈ **3,9 K/h** |

  Rund **35 % langsamer** bei praktisch gleicher Verdichterleistung — also entsprechend
  sinkender COP im oberen Bereich. Die letzten 5 K brauchten ≈ 78 min.

## Empfohlene Konfiguration

**PV-Steuerung (Coordinator):** Die Integration setzt die Grenze seit v1.15.0 selbst um.
Seit v1.16.0 gibt es **drei** Stufen (plus ELEC als separate Notfall-Option in
`emergency.py`, kein Teil der PV-Eskalation mehr) — Boost ist eine **Leistungssenke**
(WP + Heizstab gemeinsam), keine eigene Temperaturstufe:

| Stufe | Option | Bereich | Wer heizt |
|---|---|---|---|
| Normal (`base`) | `pv_temp_base` | 35–**65** °C | Verdichter (i. d. R. aus) |
| Erhöht (`normal`) | `pv_temp_normal` | 35–**65** °C | Verdichter |
| Boost | *(gleiche Zieltemp wie Erhöht, `pv_temp_normal`)* | 35–**65** °C | **Verdichter + Heizstab gemeinsam** |

`pv_temp_high` (35–**75** °C) bleibt bestehen, ist im Coordinator-Modus aber **unbenutzt**
— nur noch das Executor-Programm (`select.haier_hwhp_pv_program`, Programm „Boost“)
verwendet es für einen echten Sollwert bis 75 °C.

Empfohlen (Coordinator): **50 / 60** (Normal / Erhöht). Die WP fährt bis 60 °C allein;
Boost schaltet ab ausreichendem Überschuss zusätzlich den Heizstab dazu, ohne die
Zieltemperatur zu ändern — der Heizstab ist hier eine reine Absorptions-/Leistungsstufe
für deutlichen Überschuss, kein Weg zu einer höheren Temperatur.

Erhöht ist in der Oberfläche auf **65 °C** begrenzt, weil sie der Verdichter allein
erreichen muss — und weil Boost dieselbe Zieltemperatur nutzt, gilt die Grenze
automatisch auch für Boost. Zusätzlich prüft der Konfigurationsdialog die Reihenfolge
(`Normal < Erhöht`); `pv.py` klemmt verdrehte Werte zur Laufzeit zusätzlich ab.

**Legionellen-Schutz:** `legionella_bottom_min` **nicht** auf 65 °C setzen — das ist exakt
die WP-Maximaltemperatur, gemessen an der **kältesten** Schicht (Tank unten), und damit
sehr knapp. **60 °C** empfohlen (auch die DVGW-übliche Abtötungsschwelle), `legionella_target`
65 °C.

## Offener Punkt: geräteeigene Sterilisation

Laut Hersteller heizt das Gerät bei aktivierter Sterilisationsfunktion
(`switch.*_sterilize`) **wöchentlich selbsttätig auf 75 °C**. In der o. g. Feldbeobachtung
war der Schalter **an**, die Wassertemperatur überschritt in vier Monaten aber **nie 65 °C**.

Mögliche Erklärungen (nicht abschließend geklärt):
- Die Funktion feuert nicht (Zeitplan/Bedingung unbekannt, Modbus liefert dazu nichts).
- Sie ist ebenfalls bei 65 °C gedeckelt.
- Sie benötigt den Heizstab und wird durch eine andere Bedingung blockiert.

Wer sich nicht darauf verlassen will, nutzt den **integrierten Legionellen-Schutz** dieser
Integration (Watchdog auf die letzte verifizierte Volldurchheizung, siehe README) — der
weist den Erfolg über `Tank unten` nach, statt ihn anzunehmen.
