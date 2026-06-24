# Fehlercodes (Faults & Protection)

Anzeige-Codes der Haier-BWWP-M7-Familie laut Hersteller-Handbuch
(„Faults and protection"). Sie erscheinen auf dem Geräte-Display.

> **Modbus-Sensor:** Register 18 (`Fehlercode`) liefert eine **Zahl**, `0` = kein
> Fehler. Laut Modbus-Doku bildet sie gruppenweise auf den Anzeige-Code ab:
> **1–15 = E1–EF, 16–31 = L0–LF, 32–47 = F0–FF, 48–63 = P0–PF, 64 = PP**
> (Buchstabe + Hex-Ziffer, z. B. 34 → F2, 27 → Lb, 59 → PB). Der Sensor
> `Fehlercode` rechnet das automatisch um und zeigt **Anzeige-Code + Klartext**
> als Attribute (`code`, `description`).

| Code | Fehlertyp | Auslöser / Bedeutung | Reset |
|------|-----------|----------------------|-------|
| F2 | Verdichterschutz | Schutz Betriebstemperatur | nach Behebung automatisch |
| F3 | Verdichterschutz | Abluft-Temperaturschutz | nach Behebung Strom aus/ein |
| F5 | Verdichterschutz | Verdampfer-Übertemperaturschutz | nach Behebung Strom aus/ein |
| E1 | Stromableitungs-Alarm | zu niedrige elektrische Isolation | nach Behebung Strom aus/ein |
| E2 | Übertemperatur-Alarm | Wassertemperatur ≥ 88 °C | automatisch |
| E3 | Tank-Temperaturfühler | Kurzschluss/Unterbrechung | automatisch |
| E4 | Umgebungs-Temperaturfühler | Kurzschluss/Unterbrechung | automatisch |
| E5 | Verdampfer-Temperaturfühler | Kurzschluss/Unterbrechung | automatisch |
| E6 | Verdichter-Abluft-Temperaturfühler | Kurzschluss/Unterbrechung | automatisch |
| ED | Verdichter-Ansaug-Temperaturfühler | Kurzschluss/Unterbrechung | automatisch |
| E7 | Kommunikationsfehler | Hauptplatine ↔ Anzeige gestört | automatisch |
| E9 | Umgebungstemperatur-Schutz | < -7 °C oder > 43 °C | automatisch |
| EF | Off-Peak-Signal | kein Off-Peak-Signal vom Versorger empfangen | automatisch |
| Lb | Externer Wärmequellen-Temperaturfühler | Kurzschluss/Unterbrechung | automatisch |
| E8 | Druckschalter-Schutz | Auslösen am Auslass | nach Behebung Strom aus/ein |
| L7 | Lüfterfehler | Lüfterblatt blockiert oder Kommunikationsfehler | nach Behebung Strom aus/ein |
| F0 | WiFi-Kommunikationsfehler | Anzeige ↔ WiFi-Modul im Konfig-Modus | automatisch |
| P1 | Frequenzumrichter | Phasenstrom Hardware-Überstrom (transient) | nach Behebung Strom aus/ein |
| P2 | Frequenzumrichter | Phasenstrom Software-Überstrom (momentan) | automatisch |
| P3 | Frequenzumrichter | IPM-Temperaturanomalie | automatisch |
| P4 | Frequenzumrichter | Überlast | automatisch |
| P5 | Frequenzumrichter | Unterspannungsschutz | automatisch |
| P6 | Frequenzumrichter | Überspannungsschutz | automatisch |
| P7 | Frequenzumrichter | Kommunikation Hauptsteuerung ↔ Treiber | automatisch |
| P8 | Frequenzumrichter | Stromerkennungsschaltung (Umrichter-Seite) fehlerhaft | nach Behebung Strom aus/ein |
| PB | Frequenzumrichter | Schrittverlust-Erkennung (out of step) | nach Behebung Strom aus/ein |
| PD | Frequenzumrichter | Software-Überstrom Gleichrichter-Seite (transient) | automatisch |
| PF | Frequenzumrichter | Hardware-Überstrom Gleichrichter-Seite | nach Behebung Strom aus/ein |

„nach Behebung automatisch" = der Fehler quittiert sich selbst, sobald die
Ursache weg ist. „Strom aus/ein" = Gerät nach Behebung neu starten bzw.
Spannungsversorgung kurz trennen.
