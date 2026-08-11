# Gerätegrenzen der Haier-BWWP-M7-Familie

Wichtig für die Konfiguration der PV-Steuerung und des Legionellen-Schutzes:
**Das Modbus-Register erlaubt mehr, als das Gerät kann.**

## Temperaturgrenzen

| Größe | Wert | Quelle |
|---|---|---|
| Sollwert-Register (Reg 6) | **35–75 °C** schreibbar | Hersteller-Modbus-Doku |
| **Max. Wassertemperatur im WP-Betrieb** | **65 °C** | Herstellerangabe (s. u.) |
| **75 °C** | **nur** über die geräteeigene **Sterilisationsfunktion**, 1×/Woche | Herstellerangabe |
| Integrierter E-Heizstab | **1500 W** – „als Reserve oder zur schnellen Warmwassererzeugung im Boost-Modus" | Herstellerangabe |
| COP (Herstellerangabe) | 3,27–3,5 | Herstellerangabe |

Belegt für **HP200M7-F9** (192–200 L, R290 0,15 kg):
[KlimaWorld](https://www.klimaworld.com/haier-brauchwasserwarmepumpe-hp200m7-f9-r290-192-liter.html) ·
[heizungsdiscount24](https://www.heizungsdiscount24.de/waermepumpen/haier-hp200m7-f9-brauchwasserwaermepumpe-200-liter-r290-ohne-waermetauscher.html) ·
[heima24](https://www.heima24.de/heizung/haier-brauchwasserwaermepumpe-m7-200-liter-ohne-waermetauscher-hp200m7-f9.html)

> **Konsequenz:** Oberhalb **65 °C** arbeitet ausschließlich der **1500-W-Heizstab**
> (COP ≈ 1). Ein Sollwert von 70–75 °C ist über Modbus zwar schreibbar, wird vom
> Verdichter aber **nie allein erreicht**.

## Messtechnische Bestätigung (Feldbeobachtung)

Aus vier Monaten Langzeitstatistik einer realen HP200M7-F9:

- **Monats-Maxima der Wassertemperatur: 57 / 64 / 65 °C** — nie darüber.
- Ein vollständiger Zyklus bis **65 °C** lief **rein über den Verdichter**
  (`binary_sensor.*_status_heater` durchgehend `off`) → 65 °C sind ohne Heizstab erreichbar.
- **Messbarer Kapazitätsabfall zum Ende hin**, im selben Zyklus:

  | Bereich | Aufheizrate |
  |---|---|
  | 53 → 59 °C | ≈ **6,0 K/h** |
  | 60 → 65 °C | ≈ **3,9 K/h** |

  Rund **35 % langsamer** bei praktisch gleicher Verdichterleistung — also entsprechend
  sinkender COP im oberen Bereich. Die letzten 5 K brauchten ≈ 78 min.

## Empfohlene Konfiguration

**PV-Steuerung (Coordinator):** Die Solar-Boost-Stufe soll „WP bis an ihre Leistungsgrenze"
bedeuten — also `pv_temp_high` = **65 °C**, nicht 75. Sinnvolle Staffelung:

| Stufe | Option | Empfehlung |
|---|---|---|
| Normal | `pv_temp_base` | 50 °C |
| Erhöht | `pv_temp_normal` | 58–60 °C |
| Solar-Boost | `pv_temp_high` | **65 °C** (WP-Grenze) |

Die Reihenfolge muss echt aufsteigend sein (`base < normal < high`); sonst greift das
Sicherheitsventil in `pv.py` und die Heizstab-Stufe fällt auf das alte Verhalten zurück
(kein Warten auf den Deckel). Die Werte werden intern zusätzlich geklemmt.

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
