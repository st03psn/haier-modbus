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
  Unterlagen nicht sicher zu erkennen (die Montageanleitung bei heima24 war nicht abrufbar).

## Eigene Geräteabbilder

`docs/images/models/*.svg`, erzeugt von `tools/gen_model_svgs.py` – **selbst gezeichnet**,
keine Haier-Fotos (die Produktbilder in den PDFs sind zwar schon freigestellt, aber
urheberrechtlich geschützte Werbebilder). Maßstab 1 Einheit = 5 mm, beide Größen im selben
Maßstab. Bauform nach Datenblatt: weißer Zylinder, schwarzes Bedienfeld im Kopf, dunkle
Trennfuge Kopf/Speicher, dunkler Sockel, Luftkanal-Stutzen oben. Der Speicher ist als
„Fenster“ gezeichnet (Füllstand + Farbskala wie im Dashboard), die C-Varianten zeigen die
Rohrschlange im unteren Drittel.

Geschätzt (nicht aus dem Datenblatt): Höhe des Wärmepumpen-Kopfes (~455 mm, aus dem
Produktfoto abgeleitet) und die Lage der Rohrschlange.

## Quellen

- Haier HVAC, Produktblatt „M7 HPWH R290“ (DE, 09/2025):
  https://haierhvac.eu/sites/default/files/2025-09/250918_PF_HPWH_M7-DE.pdf
- Hornbach, technisches Datenblatt M7:
  https://media.hornbach.de/hb/technicaldatasheet/as.162982654.pdf
- HeizungsDiscount24, technisches Datenblatt M7 (Inhalt wie Haier-Produktblatt):
  https://www.heizungsdiscount24.de/pdf/Haier-M7-HPWH-R290-Technisches-Datenblatt.pdf
- Händlerangabe „1 WT“: https://www.klimaworld.com/products/haier-brauchwasserwarmepumpe-hp200m7c-f9-r290-185-liter
