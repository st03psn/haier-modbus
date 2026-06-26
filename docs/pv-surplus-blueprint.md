# PV-Überschuss-Blueprint – Funktionsweise & Tuning

Beschreibt das Verhalten des Blueprints
[`blueprints/automation/haier_modbus/pv_surplus.yaml`](../blueprints/automation/haier_modbus/pv_surplus.yaml)
(ab v1.9.0). Der Blueprint setzt nur die **Solltemperatur** der BWWP – wann der
Verdichter tatsächlich läuft, entscheidet das Gerät selbst anhand dieser Stufe.

> Dies ist die **dynamische** PV-Variante (B). Die **integrierte** Steuerung in
> der Integration (`pv.py`, Setup-Assistent) nutzt feste Schwellen und ist ein
> separater Regler – nicht beide gleichzeitig auf dieselbe Solltemperatur ansetzen.

---

## Kernidee: „verfügbarer Solarstrom"

Der PV-Überschuss-Sensor misst die **Netzeinspeisung** – also den Überschuss
*nach* Abzug des Hausverbrauchs inklusive der Wärmepumpe. Läuft die WP, drückt
ihr eigener Verbrauch den angezeigten Überschuss nach unten. Eine feste Schwelle
auf den rohen Überschuss würde dadurch pendeln.

Der Blueprint rechnet stattdessen mit:

```
verfügbar = PV-Überschuss + aktuelle WP-Aufnahme
```

Diese Summe ist **unabhängig davon, ob die WP gerade läuft** (schaltet die WP ein,
sinkt der Überschuss um genau ihren Verbrauch, der hier wieder dazukommt). Damit
ist das Pendeln an der Wurzel beseitigt.

---

## Stufen & Schaltschwellen

Drei Zielstufen, gesteuert über `verfügbar` (Standardwerte in Klammern):

| Übergang | Bedingung (`verfügbar`) | Ziel |
|---|---|---|
| → Hoch | ≥ `high_avail` (1500 W) | `temp_high` (70 °C) |
| → Normal (hoch) | ≥ `max_draw` + `buffer_on` (550 + 50 = 600 W) | `temp_normal` (65 °C) |
| Hoch → Normal | < `high_avail` − `high_hysteresis` (1500 − 400 = 1100 W) | `temp_normal` |
| → Grund | < `max_draw` − `grid_tolerance` (550 − 200 = 350 W) | `temp_base` (50 °C) |

Jede Schwelle muss `debounce` (5 min) durchgehend gehalten werden, bevor reagiert
wird. Zusätzlich wird nur **hochgesetzt**, wenn der Speicher noch unter der
Zielstufe liegt (Wasser < Ziel − 2 K).

### Hysterese

Hoch- und Rückschalten nutzen **getrennte** Schwellen:
- Normal an ab **600 W**, zurück auf Grund erst unter **350 W** → Band **250 W**.
- Hoch ab **1500 W**, zurück auf Normal erst unter **1100 W** → Band **400 W**.

Der verfügbare Solarstrom muss also deutlich unter die Einschaltschwelle fallen,
bevor zurückgeschaltet wird – kein Flattern an der Grenze.

---

## Anti-Takt-Schutz

Beide Hochschalt-Zweige tragen ein zusätzliches Gate, das häufiges Kurztakten des
Verdichters verhindert:

```
ODER( WP läuft gerade            → Stufe verlängern (Piggyback, kein neuer Start)
      WP ist ≥ min_off_time aus  → neuer Zyklus erlaubt )
```

- **Piggyback:** Läuft die WP bereits (z. B. ein Grundzyklus), wird die Zielstufe
  einfach angehoben – ein durchgehender Lauf statt eines zweiten Starts.
- **Mindest-Stillstand:** Ist die WP aus, startet ein neuer PV-Zyklus erst, wenn
  sie schon `min_off_time` (30 min) aus war. So lösen kurze Überschuss-Spitzen
  (z. B. eine vorbeiziehende Wolke) keinen sofortigen Wiederanlauf aus.

Das Runter-Regeln (Hoch→Normal, →Grund) ist davon **nicht** betroffen – absenken
darf der Blueprint jederzeit.

> Technisch nativ über `condition: state … for:` auf dem WP-Status-Binärsensor –
> kein Helfer nötig. Hinweis: Die Trigger sind flankengesteuert; ein durch die
> Sperre blockierter Start wird ggf. erst beim nächsten Überschuss-Wechsel
> nachgeholt (bewusst konservativ – eher ein Zyklus zu wenig als ein Kurztakt zu viel).

---

## Parameter (Blueprint-Inputs)

| Input | Standard | Bedeutung |
|---|---|---|
| `pv_surplus_sensor` | – | PV-Überschuss / Netzeinspeisung (W) |
| `bwwp_power_sensor` | – | Aktuelle Leistungsaufnahme der WP (W) |
| `target_number` | – | Solltemperatur-Entität (Reg 6) |
| `water_temp_sensor` | – | Speicher-/Wassertemperatur |
| `wp_status_binary` | – | Verdichter läuft (für Anti-Takt) |
| `max_draw` | 550 W | Max. Verdichteraufnahme ohne Heizstab |
| `buffer_on` | 50 W | Solar-Reserve zum Hochschalten |
| `grid_tolerance` | 200 W | Tolerierter Netzbezug bis zum Rückschalten |
| `high_avail` | 1500 W | Schwelle für die Hochstufe |
| `high_hysteresis` | 400 W | Rückschalt-Hysterese Hochstufe |
| `temp_high` / `temp_normal` / `temp_base` | 70 / 65 / 50 °C | Zielstufen |
| `debounce` | 5 min | Haltezeit je Schwelle |
| `min_off_time` | 30 min | Mindest-Stillstand vor Neustart |
| `notify_target` | – | optionaler notify-Dienst |

### Tuning-Hinweise

- **Früher anspringen, etwas Netzbezug ok:** `buffer_on` senken (auch 0). Die WP
  startet dann näher am reinen Eigenbedarf.
- **Strenger solar-only:** `buffer_on` erhöhen.
- **Länger an einem angefangenen Zyklus festhalten:** `grid_tolerance` erhöhen
  (Rückschalten erst bei größerem Netzbezug).
- **Weniger Starts/Tag:** `min_off_time` erhöhen.
- `max_draw` an die reale Maximalaufnahme der eigenen Anlage anpassen.

---

## Verwandte Doku

- Entitäts-Vertrag (für Integrations-Entwickler): [`pv-automation-entity-contract.md`](pv-automation-entity-contract.md)
- Registerkarte: [`register-map.md`](register-map.md)
