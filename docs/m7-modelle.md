# Haier M7 – Modelle und Wärmetauscher-Varianten (Recherche zu #29)

Stand der Recherche: 11/2026. Quellen siehe unten; alle Angaben aus Haier-Datenblättern,
die Haier selbst als „rein indikativ“ kennzeichnet.

## Modelle laut Haier-Datenblatt

| Modell | Register (Wärmetauscher) | Inhalt | Höhe D | Ø / Tiefe | Gewicht netto | Aufheizzeit 10→55 °C @7 °C |
|---|---|---|---|---|---|---|
| HP200M7-F9  | nein | 194 L (Hornbach-Blatt: 192 L) | 1694 mm | 600 × 620 mm | 86 kg (92 kg) | 7,8 h (8,33 h) |
| HP200M7C-F9 | **ja (1 WT)** | 185 L | 1694 mm | 600 × 620 mm | 96 kg (102 kg) | 6,71 h |
| HP250M7-F9  | nein | 250 L (246 L) | 1989 mm | 600 × 620 mm | 98 kg (104 kg) | 10,51 h |
| HP250M7C-F9 | **ja (1 WT)** | 240 L | 1989 mm | 600 × 620 mm | 107 kg (113 kg) | 10,09 h |

Werte in Klammern: abweichende Angabe im Hornbach-Datenblatt. Für alle vier gilt
gleich: 1500 W Heizstab, WP 320 W nominal / 535 W max, WP bis 65 °C, mit Heizstab 35–75 °C,
Luftkanal Ø 160 mm, Wasseranschlüsse Rp 3/4.

- **Wärmetauscher-Variante = Suffix „C“** (HP200M7**C**-F9, HP250M7**C**-F9). Händler führen
  sie als „1 WT“; Haier beschreibt sie nicht wörtlich, das Schnittbild im Datenblatt zeigt
  aber eine Rohrschlange im unteren Speicherteil. Die ~9–10 L geringeren Inhalt und die
  ~10 kg Mehrgewicht passen dazu.
- **HP160M7-F9 und HP260M7-F9** (heute in `const.MODELS`) tauchen in keinem gefundenen
  Haier- oder Händlerdokument auf. Ob es sie gibt (z. B. andere Märkte), ist **ungeklärt** –
  vor einer Änderung der Modellliste bitte am Typenschild bzw. bei Haier prüfen.
- Äußerlich unterscheiden sich mit/ohne Register laut Datenblatt-Maßtabelle nicht (A/B/C/D
  identisch). Ob die C-Variante zusätzliche seitliche Anschlüsse hat, ist aus den
  Unterlagen nicht sicher zu erkennen. Die Anleitung zeigt für die C-Varianten aber eigene
  Anschlüsse für Solar-/Kesselkreis und Fühler (siehe unten).

## M8 (seit 2.2.0 wählbar, ungetestet – #37)

| Modell | Inhalt | Maße (B × T × H) | Heizstab | WP nominal / max. |
|---|---|---|---|---|
| HP80M8-9 | 82 L | 492 × 537 × 1170 mm | 1200 W | 250 / 370 W |
| HP110M8-9 | 102 L | 492 × 537 × 1320 mm | 1200 W | 250 / 370 W |
| HP150M8-9 | 149 L | 492 × 537 × 1680 mm | 1200 W | 250 / 370 W |

Quelle: Haier „Heating Solutions EU Catalogue 2024/25“. Einstellbereich mit Heizstab
35–75 °C, Wärmepumpe allein laut Lineup-Tabelle bis 65 °C (wie M7), kein Register.
Wandgerät; Bedienfeld unter der Trennfuge.

- **Modbus:** Die [FAQ von Haier-Haustechnik](https://haier-haustechnik.de/Allgemein/FAQ-s/)
  nennt M7 **und** M8 Modbus-fähig und verlinkt für beide dieselbe Modbus-Anleitung (das
  PDF in `docs/`). Die M8-Anleitung (11/2025) zeigt aber **keinen** Modbus-Anschluss.
  Registerkarte deshalb **nicht verifiziert**.
- **In der Integration:** Modell „HP…M8-9 (ungetestet)“; eigene Bauform in der
  Speicher-Grafik; Heizstab-Vorgabe 1200 W (`const.MODEL_HEATER_POWER`, nur Vorgabe).

## Woher das Gerät von Solar/Kessel weiß (Reg 3 bit2/bit3)

Laut Haier-Betriebs- und Montageanleitung (EN, Kapitel „Connection to solar collectors“,
„Connection to gas boiler“, „Connection with boiler back up“ und 3.2.3 „External heat
source“) – gilt nur für HP200M7C-F9/HP250M7C-F9:

- **Einstellung am Gerät:** Im Parametermenü wird unter „External heat source“ *Boiler*,
  *Solar* oder *deaktiviert* gewählt („Disable this function if no external heat source
  configuration is required“). Ohne diese Einstellung nutzt das Gerät das Register nicht.
- **Kessel:** Das Gerät **fordert** den Kessel selbst an – über ein Kessel-Signalkabel
  (2 × 0,75 mm²) zum Kessel und einen eigenen Kesselfühler (Platine CN27). Nicht im
  ELEC-Modus, im Boost-Modus ja.
- **Solar:** Am Speicher sitzen zwei Solarfühler – einer für die Wärmepumpe, einer für den
  Solarregler. „If the Solar photothermal starting conditions are met, stop the heat pump
  heating and carry out solar heating.“ Die genauen Startbedingungen nennt die Anleitung
  **nicht**; ob der Solarregler zusätzlich ein Signal liefert, geht aus ihr nicht hervor.
- **Anzeige:** Das Symbol „Backup element“ im Display bedeutet laut Anleitung, dass gerade
  Kessel oder Solar genutzt wird – das entspricht vermutlich Reg 3 bit2/bit3 (nicht am Gerät
  verifiziert).
- Grenzwert laut Anleitung: Speichertemperatur bei Solar-/Kesselbetrieb max. **85 °C**.

Für die Integration heißt das: bit2/bit3 sind der vom Gerät selbst gemeldete Zustand. Bei
Geräten ohne Register (oder mit deaktivierter „External heat source“) bleiben sie 0. Die
Rohrschlange richtet sich deshalb nach dem Modell, nicht danach, ob die Sensoren aktiviert sind.

Quelle: Haier, *Heat Pump Water Heater – Operation and Installation Manual*, Modell
HP200M7-F9 (enthält die C-Varianten), z. B. https://media.adeo.com/media/4488121/media.pdf

## Eigene Geräteabbilder

`docs/images/models/*.svg`, erzeugt von `tools/gen_model_svgs.py` – **selbst gezeichnet**,
keine Haier-Fotos (die Produktbilder in den PDFs sind zwar schon freigestellt, aber
urheberrechtlich geschützte Werbebilder). Maßstab 1 Einheit = 5 mm, beide Größen im selben
Maßstab. Bauform nach Datenblatt: weißer Zylinder, schwarzes Bedienfeld im Kopf, dunkle
Trennfuge Kopf/Speicher, dunkler Sockel, zwei Luftkanal-Stutzen oben, Heizstab mit Stopfen
am Mantel. Der Speicher ist als „Fenster“ gezeichnet (Warmwasser-Schicht oben, Kaltzone
unten, wie im Dashboard); die C-Varianten zeigen die Rohrschlange im unteren Drittel – mit
derselben Funktion wie das Dashboard (`dashboard_layout.coil_markup`).

Im Dashboard selbst entsteht die Grafik zur Laufzeit in `dashboard_layout._tank_js`
(button-card-JS): Farben nach Temperatur, Übergang je nach Unterschied oben/unten,
Heizstab und Rohrschlange leuchten bei Betrieb, Werte per Tipp mit Verlauf.

Geschätzt (nicht aus dem Datenblatt): Höhe des Wärmepumpen-Kopfes (~455 mm, aus dem
Produktfoto abgeleitet), Abstand der Luftstutzen, Lage von Heizstab und Rohrschlange. Das
Bedienfeld ist bewusst größer als maßstäblich, damit es auf dem Handy erkennbar bleibt.

## Quellen

- Haier HVAC, Produktblatt „M7 HPWH R290“ (DE, 09/2025):
  https://haierhvac.eu/sites/default/files/2025-09/250918_PF_HPWH_M7-DE.pdf
- Hornbach, technisches Datenblatt M7:
  https://media.hornbach.de/hb/technicaldatasheet/as.162982654.pdf
- HeizungsDiscount24, technisches Datenblatt M7 (Inhalt wie Haier-Produktblatt):
  https://www.heizungsdiscount24.de/pdf/Haier-M7-HPWH-R290-Technisches-Datenblatt.pdf
- Händlerangabe „1 WT“: https://www.klimaworld.com/products/haier-brauchwasserwarmepumpe-hp200m7c-f9-r290-185-liter
