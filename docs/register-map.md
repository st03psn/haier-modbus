# Registerkarte Haier BWWP M7 (Modbus, Holding-Register)

Quelle: offizielle Hersteller-Doku
[`Haier-Haustechnik.de Brauchwasser-WP MODBUS Einstellung.pdf`](Haier-Haustechnik.de%20Brauchwasser-WP%20MODBUS%20Einstellung.pdf).
Native Schnittstelle: **Modbus RTU, 9600 bps, 8N1** (TCP via RTU↔TCP-Gateway).

> **Funktionscodes:** Lesen `0x03`. Schreiben **nur `0x10`** (Write Multiple
> Registers) – `0x06` wird vom Gerät mit Ausnahme `0x86` abgewiesen. Die
> Integration schreibt daher grundsätzlich mit `0x10`.

## Steuer- und Statusregister

| Adr. | Name | R/W | FC | Datenformat |
|----:|------|:--:|----|-------------|
| 0  | Slave-Adresse | R  | 0x03 | 1..254 |
| 1  | Modus (current mode) | RW | 0x03/0x10 | 0 AUTO · 1 ECO · 2 ELEC · 3 VAC |
| 2  | Funktionsschalter | RW | 0x03/0x10 | bit0 aktiv · bit1 Boost · bit2 Leise · bit3 Sterilisation |
| 3  | Betriebsstatus (current operating status / genutzte Quelle) | R | 0x03 | bit0 WP · bit1 Heizstab · bit2 Solar · bit3 Kessel |
| 4  | Warmwasser % | R | 0x03 | 0..100 |
| 5  | Zieltemperatur | R | 0x03 | °C, 1..100 |
| 6  | Solltemperatur (user set) | RW | 0x03/0x10 | °C, 35..75 — **Registergrenze, nicht Gerätegrenze**, s. u. |
| 7  | Wassertemperatur (Ist) | R | 0x03 | °C, 0..100 |
| 8  | Tank oben | R | 0x03 | °C, 0..100 |
| 9  | Tank unten | R | 0x03 | °C, 0..100 |
| 10 | Umgebungstemperatur | R | 0x03 | °C, **int16 vorzeichenbehaftet** (-50..100) |
| 11–17 | RTC (7 Register) | R | 0x03 | 11 Jahr (YY, 24=2024) · 12 Monat · 13 Tag · 14 Woche (1–7) · 15 Std · 16 Min · 17 Sek |
| 18 | Fehlercode | R | 0x03 | 0 keiner; 1–15 E1–EF; 16–31 L0–LF; 32–47 F0–FF; 48–63 P0–PF; 64 PP |

> **Registergrenze ≠ Gerätegrenze:** Reg 6 nimmt bis **75 °C** an. Das Hersteller-Datenblatt
> unterscheidet aber **„Einstellbereich mit Heizstab 35–75 °C"** von **„max.
> Temperaturausgabe nur Wärmepumpe 65 °C"** — der Bereich 65–75 °C ist nur mit dem
> 1500-W-Heizstab erreichbar. Datenblatt-Belege, Feldmessungen und
> Konfigurationsempfehlungen: [`geraete-grenzen.md`](geraete-grenzen.md).

## Energie-/Wärmeregister (kWh)

Jeder Block umfasst **24 Register**: **7 Tageswerte (Mo–So) + 12 Monatswerte
(Jan–Dez) + 5 Jahreswerte (vor 4 Jahren … dieses Jahr)**. Die PDF beschreibt sie
byte-weise (2 Byte = 1 Register); „dieses Jahr" = letztes Register des Blocks.

| Größe (PDF) | Tage | Monate | Jahre | dieses Jahr |
|---|---|---|---|:--:|
| Kompressor-/WP-Strom (压缩机耗电量) | 19–25 | 26–37 | 38–42 | **42** |
| Heizstab-Strom (电加热耗电量) | 43–49 | 50–61 | 62–66 | **66** |
| Wärmemenge erzeugt (累计制热量) | 67–73 | 74–85 | 86–90 | **90** |

## COP

```
COP(Jahr) = Wärmemenge(90) / ( WP-Strom(42) + Heizstab-Strom(66) )
```

Monatlich analog über die Monatsblöcke (Wärme 74–85, WP 26–37, Heizstab 50–61).

### Vor Nutzung verifizieren (kritisch)

**Begriffsklärung:** Die englische PDF-Zeile „Accumulated energy consumption
(heating power)" ist irreführend (klingt nach Stromverbrauch). Der chinesische
Originalbegriff `累计制热量` bedeutet *akkumulierte erzeugte Wärmemenge* (`制热量`
= Wärme-Erzeugung), im Gegensatz zu `耗电量` (= Stromverbrauch) der beiden
anderen Blöcke. Register 90 ist demnach **erzeugte Wärme**, nicht Strom.

> **Hinweis zum früheren „COP ≈ 0,11":** Der einmalig beobachtete Wert (Wärme
> 60 kWh ÷ Strom ~545 kWh) war **kein** echter Messwert, sondern ein Artefakt:
> Der Gesamt-Stromzähler war versehentlich auf den **Lebenswert** der externen
> Quelle (Shelly, ~524 kWh) vorbefüllt worden. Das ist behoben (Totale starten
> bei 0). Bei verbleibenden Alt-Ausreißern hilft der Dienst
> `haier_modbus.reset_energy_statistics`.

### System-COP vs. Geräte-COP

Der berechnete COP/JAZ ist ein **System-COP**: Bei externer Stromquelle (Shelly)
steckt die **real gemessene** Energie drin – **inkl. Standby, Steuerelektronik
und Lüfter**. Der **geräteinterne** Zähler (Reg 42/66) bilanziert
dagegen offenbar nur den **Betriebsverbrauch** während aktiver Heizphasen, **ohne
Nebenverbraucher/Standby**, ist auf **ganze kWh** gerundet und liegt erfahrungs-
gemäß **deutlich (teils um ein Vielfaches) zu niedrig**. Der Geräte-COP fällt
dadurch zu optimistisch aus. **Für eine belastbare JAZ den externen Stromzähler
nutzen**, den Geräte-Zähler nur als groben Anhaltspunkt.

Die offene Frage ist also Existenz *und* Qualität:

1. **Realität:** Schwankt Register 90 über Tage *unabhängig* vom Strom (z. B. COP
   sinkt bei Kälte)? Dann echte Kalorimetrie. Ist es stur Strom × Konstante, ist
   der „COP" zirkulär – dann externe Wärmequelle nutzen.
2. **Skalierung:** 16-bit (max 65535). Jahreswert gegen bekannte Referenz prüfen
   (z. B. Shelly-Strom) → `energy_scale` (×1 oder ×0.1) im Options-Dialog setzen.
3. **Jahres-Reset:** Wann springt „dieses Jahr" auf 0 (geräteinterne RTC)? Für
   externe Stromquelle einen jährlich zurücksetzenden utility_meter wählen, damit
   die Fenster zueinander passen.

## Basis-Einstellungen am Haier-Bedienteil

Adresse 1–254 · Modus RTU · 9600 bps · 1 Startbit · 8 Datenbits · keine Parität ·
1 Stoppbit.

## Adressierung

pymodbus adressiert PDU-basiert; die Adressen oben entsprechen den Holding-
Register-Adressen der Doku. Falls alle Werte um 1 verschoben erscheinen,
`READ_START` / die Adressen in `const.py` um 1 anpassen.
