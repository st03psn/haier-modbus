# Umsetzungsplan: PV-Steuerung — Betriebsmodi (Aus / Coordinator / Executor) + Überschuss-Modell

> Status: **geplant, noch nicht umgesetzt.** In frischer Sitzung implementieren.
> Betrifft `custom_components/haier_modbus/pv.py`, `config_flow.py`, `const.py`,
> Übersetzungen, `__init__.py` (Migration), `select.py` (neue Programm-Entität) und Doku.
> Erarbeitet 2026-06-28.

---

## 1. Architektur: Coordinator- vs. Executor-Rolle

Die Integration trennt sauber **Mechanik** (die „Regelprogramme": Sollwert 50/65/75,
Modus ECO/AUTO, Boost/Heizstab — als HA-Entitäten + Modbus-Writes über den
`DataUpdateCoordinator`) von der **Politik** (welches Programm jetzt gelten soll).

Wer die Politik macht, wählt ein **Dropdown** in der Konfiguration
(ersetzt den bisherigen Bool-Haken „PV-Überschuss-Steuerung aktiv"):

| Modus | Wer entscheidet | Was die Integration tut |
|---|---|---|
| **Aus** | niemand (nur Geräte-ECO/manuell) | nichts; nur die rohen Entitäten + 38°-Guard |
| **Coordinator** | **die Integration** (`pv.py`) | regelt selbst nach Überschuss + Morgen-Start (Kap. 2) |
| **Executor (HEMS-Client)** | **externes HEMS** (z. B. evcc) | regelt NICHT selbst; stellt die Programme bereit, das HEMS triggert sie (Kap. 3) |

Gemeinsam für alle Modi:
- Die **Stell-Entitäten bleiben immer beschreibbar** (`number.haier_hwhp_set_temp`,
  `select.haier_hwhp_mode`, Boost-Switch) — egal welcher Modus.
- Der **38-°C-Guard (`emergency.py`)** ist **unabhängig** von diesem Modus (eigener
  Haken) und bleibt als lokales WW-Sicherheitsnetz aktiv.
- Es regelt immer nur **EIN** Gehirn (kein Doppelregler) — genau dafür ist das Dropdown.

### Warum das Überschuss-Modell (statt `verfügbar`)
`sensor.pv_uberschuss_watt` **kappt bei 0** (kein signierter Netzwert) → sobald die WP
läuft, ist `verfügbar = surplus + Aufnahme` nicht mehr solar/netz-unterscheidbar.
Überschuss-Spitze real nur ~350–650 W. Gerät-ECO: feste Wiedereinschalt-Hysterese
~6–7 K, Heizfenster hart am Gerät verdrahtet (~10–18 h, HA kennt es nicht). Großer
Sollsprung (50→65) startet die WP auch in ECO sofort.

---

## 2. Coordinator-Modus — Verhalten (Überschuss-Modell + Morgen-Start)

Nur `sensor.pv_uberschuss_watt` (roh, ≥ 0). Drei Zielstufen 50/65/75.

1. **Morgen-Start (fix):** Zur Uhrzeit (Default **10:00** = ECO-Fensterstart), **einmal/Tag**,
   wenn **Wasser < Grundtemp (50)** und Sollwert < 65 und Anti-Takt erlaubt → Sollwert **65**.
2. **Bei 65 bleiben**, solange Überschuss > **Halte-Schwelle** (Default 50 W).
3. **Runter auf 50:** Überschuss < Halte-Schwelle für **Entprellzeit (5 min)** → Sollwert 50
   (Wasser i. d. R. < 50 → heizt bis 50 fertig, stoppt; sonst stoppt bei erreichter Temp).
4. **Wiederanlauf (Option, Default an):** kommt tagsüber wieder Überschuss >
   **Wiederanlauf-Schwelle** (Default 200 W) → erneut 65; Anti-Takt: WP läuft (Piggyback)
   ODER ≥ **Mindest-Stillstand** (30 min) aus.
5. **75 + Eskalation (Boost/ELEC):** bei Überschuss > **Hoch-Schwelle** (Default 1200 W,
   selten) und laufender WP. Eskalation wie bisher (`pv_escalation`).

Entprellung auf alle Stufenwechsel; Pendelschutz durch einmaligen Morgen-Start + debounced
Wiederanlauf mit Mindest-Stillstand.

### Verifikations-Szenarien
- **2-Min-Wolke bei 55/Soll 65:** Entprellung ignoriert → bleibt 65. Nur anhaltend (≥5 min)
  kein Überschuss → 50, stoppt bei erreichter Temp.
- **Morgenstart 65 bei Wasser 49, dann Klima frisst Überschuss:** nach 5 min → Soll 50;
  Wasser ~49–50 → heizt bis 50 fertig, stoppt. Grundversorgung gesichert, 65 verworfen. ✅
- **Trüber Morgen:** Start setzt 65 → nach Entprellung 50 → heizt bis 50 (punktuelle WW).
  Nachmittags-Sonne + Wiederanlauf an → erneut 65.

### `pv.py` Kernlogik (Pseudocode, nur im Coordinator-Modus)
```
async_evaluate(coordinator, data):
    o = entry.options
    if o[PV_MODE] != "coordinator": reset(); return     # Aus/Executor -> pv.py inert
    surplus = state_float(o[PV_SENSOR])                  # roh, ≥0
    if surplus is None: return
    now = dt_util.now()
    running = bool((data[REG_STATUS] or 0) & STATUS_HEATPUMP)
    if running: _off_since = None
    elif _was_running: _off_since = now
    _was_running = running
    current = float(data[REG_SET_TEMP]);  if None: return
    water = float(data[REG_WATER_TEMP] or 0)
    t_high, t_normal, t_base = temps(o)

    # 1) Morgen-Start (einmal/Tag)
    if o[MORNING_ENABLED] and now.time() >= parse(o[MORNING_TIME]) and _last_kick_day != now.date():
        _last_kick_day = now.date()
        if water < t_base and current < t_normal and _start_allowed(o, running, now):
            write(REG_SET_TEMP, int(t_normal)); announce(up); return

    # 2) Stufenlogik aus Roh-Überschuss (Hysterese über cur_tier) + Entprellung
    cur = tier_of(current, t_high, t_normal)
    desired = _desired(o, surplus, cur)                  # high/normal/base (s.u.)
    if desired != _candidate: _candidate = desired; _since = now; return
    if (now - _since) < o[DEBOUNCE]: return
    target = {'high':t_high,'normal':t_normal,'base':t_base}[desired]
    if int(current) != int(target):
        if target < current:                              # runter immer
            write(REG_SET_TEMP, int(target)); announce(down)
        else:                                             # hoch (Wiederanlauf/High)
            up_ok = (desired=='high') or o[RERAISE_ENABLED]
            if water < target and up_ok and _start_allowed(o, running, now):
                write(REG_SET_TEMP, int(target)); announce(up)
    apply_escalation(coordinator, o, data, desired=='high' and running, surplus)

_desired(o, surplus, cur):
    high=o[PV_HIGH]; reraise=o[RERAISE_THRESHOLD]; hold=o[PV_HOLD]
    if cur=='base':   return 'high' if surplus>=high else ('normal' if surplus>=reraise else 'base')
    if cur=='normal': return 'high' if surplus>=high else ('normal' if surplus>=hold else 'base')
    return ('high' if surplus>=high else 'normal') if surplus>=hold else 'base'   # cur=='high'

_start_allowed(o, running, now):
    if running: return True
    if _off_since is None: return True
    return (now - _off_since) >= o[MIN_OFF]
```

---

## 3. Executor-Modus (HEMS-Client) — Programme bereitstellen, HEMS triggert

`pv.py` regelt **nicht** (`async_evaluate` steigt sofort aus). Stattdessen stellt die
Integration die „Regelprogramme" als **Auswahl-Entität** bereit, die ein HEMS (oder der
Nutzer) setzt; die Integration übersetzt das Programm in die Mechanik.

### Neue Entität: `select.haier_hwhp_pv_program`
Optionen → Wirkung (idempotenter Write bei Auswahl):
| Programm | Wirkung |
|---|---|
| `aus` | Integration fasst den Sollwert nicht an (manuell/Gerät) |
| `grund` | Sollwert = Grundtemp (50), Modus ECO |
| `ueberschuss` | Sollwert = Normaltemp (65); optional Modus AUTO, um den ECO-Deadband sofort zu überwinden |
| `boost` | Sollwert = Hochtemp (75) + Boost (WP+Heizstab) |

- Nur im Executor-Modus aktiv/wirksam (in Aus/Coordinator ignoriert bzw. ausgeblendet).
- Alternativ/zusätzlich Service `haier_modbus.set_pv_program` mit demselben Mapping, falls
  ein HEMS lieber einen Dienst aufruft als eine Select zu setzen.
- Anwenden geschieht beim Setzen der Select (Event-getrieben), kein Dauer-Loop nötig.

### Was das HEMS lesen/steuern kann (für optimale Laufzeit & Effizienz)
**Lesen (Status fürs HEMS):**
- `sensor.haier_hwhp_water_temp` (Speichertemp), `binary_sensor.haier_hwhp_status_wp`
  (Verdichter läuft), `sensor.shelly_hz_bwwp_power` (Aufnahme), `sensor.haier_hwhp_set_temp`.

**Steuern (eine der beiden Ebenen, nicht beide mischen):**
- **Hoch-Ebene:** `select.haier_hwhp_pv_program` setzen (aus/grund/ueberschuss/boost) —
  empfohlen, da die Integration die Details (Sollwert/Modus/Boost) kapselt.
- **Tief-Ebene:** direkt `number.haier_hwhp_set_temp` (+ Modus/Boost) — wenn das HEMS
  die genauen Werte selbst bestimmen will.

**Strategie für optimale Laufzeit/Effizienz (Doku-Empfehlung fürs HEMS):**
- **Ein tiefer Zyklus/Tag** bei gutem Überschuss (z. B. `ueberschuss`/`boost`) → bankt viel
  Solarwärme, überbrückt 1–2 Tage → wenige, lange Zyklen statt vieler kurzer (besser für
  COP + Lebensdauer).
- **Kurztakten vermeiden:** HEMS soll Programmwechsel **entprellen** und einen
  **Mindest-Stillstand** zwischen Starts einhalten (die WP-eigene 6–7-K-Hysterese hilft zusätzlich).
- **AUTO nur, wenn nötig** (Deadband sofort überwinden); sonst ECO für Effizienz.
- **Boost/Heizstab** nur bei wirklich hohem Überschuss (COP ≈ 1, sonst Netz).
- **38-°C-Guard an lassen** als lokales Sicherheitsnetz (greift am Modus, nicht am Sollwert
  → ergänzt das HEMS, statt zu kollidieren).
- evcc kennt die WP nicht nativ → Brücke: *evcc-Entscheidung → MQTT/HA → Select/Sollwert*.
  Nicht gleichzeitig per Modbus direkt schreiben (zwei Master auf dem Bus vermeiden).

---

## 4. Datei-Änderungen

### `const.py`
- **Modus:** `CONF_PV_MODE` (str) + `PV_MODE_OFF="off"`, `PV_MODE_COORDINATOR="coordinator"`,
  `PV_MODE_EXECUTOR="executor"`, `DEFAULT_PV_MODE=PV_MODE_OFF`. (Ersetzt `CONF_PV_ENABLED`;
  letzteren als Legacy nur für die Migration behalten.)
- **Coordinator-Schwellen (neu, auf Roh-Überschuss):** `CONF_PV_HOLD`(50), `CONF_PV_RERAISE_THRESHOLD`(200),
  `CONF_PV_RERAISE_ENABLED`(True), `CONF_PV_MORNING_ENABLED`(True), `CONF_PV_MORNING_TIME`("10:00").
  `CONF_PV_HIGH` als Roh-Überschuss-Schwelle (Default 1200) weiterverwenden.
- **Executor:** `PV_PROGRAM_*` Konstanten (aus/grund/ueberschuss/boost).
- **Behalten:** `CONF_PV_SENSOR`, `CONF_PV_TEMP_HIGH/NORMAL/BASE`, `CONF_PV_DEBOUNCE`,
  `CONF_PV_MIN_OFF`, `CONF_PV_ESCALATION`+`PV_ESC_*`.
- **Entfernen:** `CONF_PV_BWWP_SENSOR`, `CONF_PV_NORMAL` (+`DEFAULT_PV_NORMAL`),
  `CONF_PV_HYSTERESIS` (+`DEFAULT_PV_HYSTERESIS`). **Exakte Symbol-Landkarte mit Fundstellen
  in Kap. 8.** (Die früher hier genannten `max_draw`/`buffer_on`/`grid_tolerance`/
  `high_hysteresis` waren **Blueprint-Inputs** und existieren in der Integration **nicht**.)

### `pv.py`
- Kernlogik aus Kap. 2; ganz oben `if o[PV_MODE] != COORDINATOR: reset(); return`.
- `apply_escalation`, `announce`/Logbuch (Dedup) übernehmen.

### `select.py`
- Neue `select.haier_hwhp_pv_program` (Kap. 3) — nur im Executor-Modus relevant.
  Set-Handler übersetzt Programm → `write_value` (Sollwert/Modus/Boost).

### `config_flow.py` (`_pv_schema`)
- `pv_enabled`(bool) → `pv_mode` (SelectSelector: off/coordinator/executor, translation_key).
- Coordinator-Felder: pv_sensor, temps, pv_hold, pv_reraise_threshold, pv_reraise_enabled,
  pv_high, pv_debounce, pv_min_off, pv_morning_enabled, pv_morning_time (TimeSelector), pv_escalation.
- Raus: pv_bwwp_sensor, pv_hysteresis, pv_normal(verfügbar), max_draw, buffer_on, grid_tolerance,
  high_hysteresis. Imports bereinigen.

### Übersetzungen (`strings.json`, `translations/en.json`, `translations/de.json`)
- `selector.pv_mode.options` (off/coordinator/executor), `selector.pv_program.options`.
- Alte PV-Feld-Strings raus, neue rein (config-Step + options-Step, data + data_description).
- Entity-Name für `pv_program` Select.

### `__init__.py` — Migration (`_migrate_legacy_options` erweitern)
- `pv_enabled` True → `pv_mode="coordinator"`; False/fehlt → `pv_mode="off"`; alten Key löschen.
- Alte verfügbar-PV-Keys entfernen (s. o.), neue Defaults greifen.
- COP- und Eskalations-Migration NICHT anfassen.

---

## 5. Doku (umzusetzen mit dem Feature)

In README (DE+EN) eine Sektion „PV-Überschuss — Betriebsmodi" ergänzen, die Kap. 1 + 3
nutzerfreundlich beschreibt:
- **Aus / Coordinator / Executor** erklären (wann was).
- **Executor/HEMS:** wie evcc anbindet (Select/Sollwert über HA, nicht direkt Modbus),
  welche Sensoren das HEMS lesen kann, und die **Effizienz-Strategie** (tiefe Zyklen,
  Kurztakt vermeiden, AUTO sparsam, Boost nur bei Überschuss, 38°-Guard als Netz).
- Klarstellen: immer nur **ein** Gehirn; 38°-Guard ist separat und bleibt an.

---

## 6. Defaults / Release / Checks

| Param | Default |
|---|---|
| PV-Modus | Aus |
| Morgen-Start | an, 10:00 |
| Halte-Schwelle | 50 W |
| Wiederanlauf | an, 200 W |
| Hoch-Schwelle | 1200 W |
| Entprellzeit | 5 min |
| Mindest-Stillstand | 30 min |
| Zieltemps | 50 / 65 / 75 |

- Version-Bump (Feature → 2. Stelle): **v1.11.0** in `manifest.json`.
- Checks vor Commit: `python -m py_compile custom_components/haier_modbus/*.py`,
  `python -m pyflakes custom_components/haier_modbus/`, JSON-Validierung der 3 Übersetzungen.
- Commit (`Co-Authored-By`-Trailer), Tag `v1.11.0`, push, GitHub-Release via
  `gh` ("$ProgramFiles\GitHub CLI\gh.exe", nicht im PATH).
- Danach im HA-Dialog Modus wählen; bei Coordinator den PV-Sensor `pv_uberschuss_watt`
  setzen; HA-Neustart + Browser-Hardrefresh (Übersetzungs-Cache).

## 7. Nicht anfassen
- `emergency.py` (38-°C-Guard) — separat, bleibt WW-Sicherung außerhalb des ECO-Fensters.
- Geräte-ECO-Fenster (hart am Gerät; 10:00 ist nur Konfig-Wert für den Morgen-Start).
- Brand-Icon, COP/Energie, Dashboard.

---

## 8. Exakte Symbol-Landkarte (Stand v1.10.6, Zeilen indikativ)

| Symbol | Aktion | Fundstellen (Datei:Zeile ca.) |
|---|---|---|
| `CONF_PV_ENABLED` | **ersetzen** durch `CONF_PV_MODE` | const.py:46 · config_flow.py:39,145,261 · pv.py:33,162 |
| `CONF_PV_BWWP_SENSOR` | **entfernen** | const.py:48 · config_flow.py:37,146 · pv.py:31,170 |
| `CONF_PV_NORMAL` / `DEFAULT_PV_NORMAL` | **entfernen** | const.py:50,82 · config_flow.py:44,62,148 · pv.py:38,47,125 |
| `CONF_PV_HYSTERESIS` / `DEFAULT_PV_HYSTERESIS` | **entfernen** | const.py:51,67 · config_flow.py:42,60,149 · pv.py:36,45,126 |
| `CONF_PV_HIGH` / `DEFAULT_PV_HIGH` | **behalten**, Bedeutung „verfügbar"→„Roh-Überschuss", Default 1500→**1200** | const.py:49,81 · config_flow.py:41,59,147 · pv.py:35,44,124 |
| `CONF_PV_TEMP_HIGH/NORMAL/BASE` (+Defaults) | behalten | const.py:52-54,83-85 · config_flow.py · pv.py:113-115 |
| `CONF_PV_DEBOUNCE`, `CONF_PV_MIN_OFF` (+Defaults) | behalten | const.py:55-56,68,86 · config_flow.py · pv.py:157,195 |
| `CONF_PV_ESCALATION` + `PV_ESC_*` (+Default) | behalten | const.py:58-62 · config_flow.py:40,70-72,87,156 · pv.py:34,53-55,226-228 |
| `CONF_PV_BOOST` / `CONF_PV_FORCE_ELEC` | behalten (nur Legacy-Migration) | const.py:64-65 · __init__.py:21,23,230-236 |
| `CONF_PV_SENSOR` | behalten (auch von `dashboard.py:24,127` für PV-Tile genutzt) | const.py:47 · config_flow.py · pv.py:166 · dashboard.py |

**Neu anlegen:** `CONF_PV_MODE` + `PV_MODE_OFF/COORDINATOR/EXECUTOR` (+`DEFAULT_PV_MODE`),
`CONF_PV_HOLD`(+Default 50), `CONF_PV_RERAISE_THRESHOLD`(+Default 200),
`CONF_PV_RERAISE_ENABLED`(Default True), `CONF_PV_MORNING_ENABLED`(Default True),
`CONF_PV_MORNING_TIME`(+Default "10:00"), `CONF_PV_PROGRAM` + `PV_PROGRAM_OFF/GRUND/UEBERSCHUSS/BOOST`.

> Vor dem Entfernen je Symbol erneut `grep` (Zeilen verschieben sich). Nach jeder Datei
> `pyflakes` laufen lassen, damit keine ungenutzten Imports übrig bleiben.

## 9. Erster Schritt: Branch
```
git checkout -b feature/pv-modes
```
Umbau isoliert entwickeln, statisch prüfen, committen; **nach Live-Test** nach `main`
mergen + taggen (v1.11.0) + Release. (Kein Direkt-Commit auf main.)

## 10. Verifikations-Checkliste (lokal kein HA → live prüfen)

**Statisch (vor Commit):** `py_compile custom_components/haier_modbus/*.py`,
`pyflakes custom_components/haier_modbus/`, JSON der 3 Übersetzungen valide.

**Nach HACS-Update + HA-Neustart + Browser-Hardrefresh:**
1. **Dialog:** „PV-Modus"-Dropdown zeigt Aus/Coordinator/Executor. Bei Coordinator
   erscheinen die Schwellen-Felder; bei Executor die Programm-Select. Keine Rohschlüssel
   als Labels (sonst Übersetzungs-Cache → Neustart/Hardrefresh).
2. **Migration:** Bestand mit altem Haken „an" → Modus = Coordinator; „aus"/leer → Aus.
3. **Coordinator:**
   - Vor 10:00 Wasser < 50 → um 10:00 springt `number.haier_hwhp_set_temp` auf 65
     (Logbuch „BWWP PV-Überschuss"); am Sollwert-Verlauf prüfen.
   - Überschuss > Halte → bleibt 65; Überschuss ≥ 5 min weg → 50 (heizt bis 50, stoppt).
   - Wiederanlauf an: nach Drop + Überschuss > 200 W (≥ Entprellung, WP ≥30 min aus/läuft) → erneut 65.
4. **Executor:** Modus = Executor → `select.haier_hwhp_pv_program` setzen:
   `ueberschuss`→Soll 65 · `grund`→50 · `boost`→75 + Boost-Switch an · `aus`→kein Eingriff.
5. **38°-Guard:** unabhängig vom PV-Modus — bei Wasser < kritisch springt Modus ECO→AUTO
   (testweise `emergency_critical` kurz hochsetzen).

## 11. evcc-Anbindung (Executor) — Beispiel

evcc entscheidet, HA führt aus. Robusteste Brücke: evcc liefert seinen Überschuss/Status
per MQTT, eine **HA-Automation** mappt das auf das Programm-Select (nicht direkt Modbus —
kein zweiter Bus-Master):

```yaml
# evcc publiziert z. B. sensor.evcc_pv_surplus (W, Überschuss nach Priorisierung Auto/Batterie)
automation:
  - alias: "BWWP-Programm aus evcc-Überschuss"
    trigger:
      - trigger: state
        entity_id: sensor.evcc_pv_surplus
        for: { minutes: 5 }            # Entprellung gegen Wolken
    action:
      - action: select.select_option
        target: { entity_id: select.haier_hwhp_pv_program }
        data:
          option: >
            {% set s = states('sensor.evcc_pv_surplus') | float(0) %}
            {% if s >= 1000 %}boost{% elif s >= 200 %}ueberschuss{% else %}grund{% endif %}
```
Voraussetzung: **PV-Modus = Executor** (sonst regelt der Coordinator gegen). Alternativ
kann evcc den Sollwert direkt setzen (`number.set_value` auf `number.haier_hwhp_set_temp`),
wenn es die Temperaturen selbst bestimmen will. 38°-Guard bleibt als Netz aktiv.

