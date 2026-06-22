# Registerkarte HP200M7-F9 (Modbus, Holding-Register, FC 0x03)

Quelle: offizielle Hersteller-Doku „Haier-Haustechnik.de Brauchwasser-WP MODBUS Einstellung".
Native Schnittstelle: **Modbus RTU, 9600 bps, 8N1** (TCP via RTU↔TCP-Gateway).

## Steuer- und Statusregister

| Adr. | Name | Z. | Bedeutung |
|----:|------|:--:|-----------|
| 0  | Slave-Adresse | R  | 1..254 |
| 1  | Modus | RW | 0 AUTO · 1 ECO · 2 ELEC · 3 VAC |
| 2  | Funktionsschalter | RW | bit0 aktiv · bit1 Boost · bit2 Leise · bit3 Sterilisation |
| 3  | Betriebsstatus | R | bit0 WP · bit1 Heizstab · bit2 Solar · bit3 Kessel |
| 4  | Warmwasser % | R | 0..100 |
| 5  | Zieltemperatur | R | °C |
| 6  | Solltemperatur | RW | °C, 35..75 |
| 7  | Wassertemperatur (Ist) | R | °C |
| 8  | Tank oben | R | °C |
| 9  | Tank unten | R | °C |
| 10 | Umgebungstemperatur | R | °C, **int16 vorzeichenbehaftet** (-50..100) |
| 11–17 | RTC (Jahr/Monat/Tag/Woche/Std/Min/Sek) | R | – |
| 18 | Fehlercode | R | 0 keiner; 1–15 E1–EF; 16–31 L0–LF; 32–47 F0–FF; 48–63 P0–PF; 64 PP |

## Energie-/Wärmeregister (kWh)

Jeder Block: **7 Tageswerte (Mo–So) + 12 Monatswerte (Jan–Dez) + 5 Jahreswerte
(vor 4 Jahren … dieses Jahr)**. „Dieses Jahr" = letztes Register des Blocks.

| Größe | Tage | Monate | Jahre | dieses Jahr |
|---|---|---|---|:--:|
| Kompressor-/WP-Strom | 19–25 | 26–37 | 38–42 | **42** |
| Heizstab-Strom | 43–49 | 50–61 | 62–66 | **66** |
| Wärmemenge (erzeugt) | 67–73 | 74–85 | 86–90 | **90** |

## COP

```
COP(Jahr) = Wärmemenge(90) / ( WP-Strom(42) + Heizstab-Strom(66) )
```

Monatlich analog über die Monatsblöcke (Wärme 74–85, WP 26–37, Heizstab 50–61).

### Vor Nutzung verifizieren (kritisch)

1. **Realität:** Schwankt Register 90 über Tage *unabhängig* vom Strom (z. B. COP sinkt
   bei Kälte)? Dann echte Kalorimetrie. Ist es stur Strom × Konstante, ist der „COP"
   zirkulär und wertlos – dann externe Quellen nutzen.
2. **Skalierung:** 16-bit (max 65535). Jahreswert gegen bekannte Referenz prüfen
   (z. B. Shelly-Strom ~525 kWh) → `energy_scale` (×1 oder ×0.1) im Options-Dialog setzen.
3. **Jahres-Reset:** Wann springt „dieses Jahr" auf 0 (geräteinterne RTC)? Für
   externe Stromquelle einen jährlich zurücksetzenden utility_meter wählen, damit
   die Fenster zueinander passen.

## Adressierung

pymodbus adressiert PDU-basiert. Falls alle Werte um 1 verschoben erscheinen,
`READ_START` / die Adressen in `const.py` um 1 anpassen und mit dem bisher
funktionierenden YAML abgleichen.
