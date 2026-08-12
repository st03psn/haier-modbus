# CLAUDE.md

Arbeitshinweise für Claude Code in diesem Repository.

## Projekt

Home-Assistant-Custom-Integration (HACS) für **Haier Brauchwasserwärmepumpen der
M7-Familie** (HP160/200/260M7-F9) über **Modbus RTU→TCP**. Sprache im Code, in Kommentaren,
Doku und Commits: **Deutsch**.

## Aufbau

```
custom_components/haier_modbus/
  coordinator.py   Block-Read (Reg 1..90) je Intervall + Schreibzugriffe; hält die Controller
  pv.py            PV-Überschuss-Regelung (nur Coordinator-Modus) – 2 Schichten
  emergency.py     Notfall-Nachheizung ECO→AUTO bei kritischer Wassertemperatur
  legionella.py    Legionellen-Watchdog (periodische thermische Desinfektion)
  energy.py        Energie-Akkumulator + COP/JAZ
  config_flow.py   Setup-Assistent + Options-Flow (alles über die UI)
  number/sensor/select/switch/binary_sensor/water_heater.py   Entitäten
  dashboard.py     Mitgeliefertes Storage-Dashboard
  const.py         Register-Karte, Options-Keys, Defaults
docs/
  register-map.md     Modbus-Register (Quelle: Hersteller-PDF im selben Ordner)
  geraete-grenzen.md  Temperatur-/Leistungsgrenzen des Geräts – VOR Regelungsarbeit lesen
  fault-codes.md      Fehlercode-Tabelle
  pv-executor-evcc.md HEMS-Anbindung (evcc)
```

Die drei Controller (`pv`, `emergency`, `legionella`) werden vom Coordinator **in dieser
Reihenfolge** je Poll ausgewertet: Legionellen zuerst (besitzt bei aktivem Lauf Sollwert und
Modus), dann PV, dann Notheizung. Wer schreibt, tritt zurück, wenn ein höher priorisierter
Controller aktiv ist.

## Harte Regeln

1. **Kein zweiter Bus-Master.** Alles läuft über den Coordinator; niemals parallel per YAML
   `modbus:` auf dasselbe Gerät schreiben.
2. **Schreiben nur mit FC 0x10** (`write_registers`). Das Gerät weist FC 0x06 mit Ausnahme
   `0x86` zurück — siehe `docs/register-map.md`.
3. **Register-Grenzen ≠ Gerätegrenzen.** Reg 6 nimmt 35–75 °C an (`SET_TEMP_MAX`), der
   Verdichter erreicht aber nur **65 °C** (`WP_MAX_TEMP`); darüber arbeitet ausschließlich
   der 1500-W-Heizstab. Das Datenblatt führt beides als getrennte Zeilen — Belege in
   `docs/geraete-grenzen.md`. Konsequenz im Code: Stufen, die der **Verdichter allein**
   fahren muss (Normal/Erhöht, Solar-Boost-Ziel), sind auf `WP_MAX_TEMP` zu begrenzen;
   nur die Heizstab-Stufe darf bis `SET_TEMP_MAX`. Bei jeder Arbeit an Zieltemperaturen
   prüfen, in welche der beiden Klassen ein Wert gehört.
4. **Eine Quelle der Wahrheit.** Einstellungen leben in `entry.options`. Neue
   Bedien-Entitäten sind Fassaden darauf, kein Parallelspeicher.
5. **Kein Reload für Laufzeit-Optionen.** Keys in `LIVE_OPTION_KEYS` (`const.py`) werden von
   `pv.py` je Poll frisch gelesen; `_async_update_listener` überspringt dafür den Reload.
   **Grund:** Ein Reload baut die Controller neu und verwirft In-Memory-Besitzstände ohne
   Persistenz (`_boost_applied`, `_prev_mode`, `_manual_hold`, `emergency._forced`,
   `legionella._saved_setpoint`). Folge sonst: Boost-Bit bleibt dauerhaft gesetzt bzw. das
   Gerät hängt in ELEC (COP ≈ 1). Wer eine Option ergänzt, die nur zur Laufzeit gelesen wird,
   nimmt sie in `LIVE_OPTION_KEYS` auf.
6. **Übersetzungen dreifach pflegen:** `translations/de.json`, `translations/en.json` und
   `strings.json` (Letztere spiegelt die englische Fassung). Config-/Options-Flow-Felder
   stehen in **zwei** Blöcken je Datei (`config.step.pv_details` **und** `options.step.pv`) —
   `hassfest` prüft die Vollständigkeit.
7. **Versionierung:** Feature = 2. Stelle, Bugfix = 3. Stelle (`CHANGELOG.md`-Kopf).
   `manifest.json` und CHANGELOG immer gemeinsam anheben.

## Regelungslogik – Fallstricke

Diese Punkte haben in der Vergangenheit reale Fehler verursacht:

- **Piggyback-Prinzip:** Der Sollwert wird tagsüber **nur bei bereits laufender WP**
  angehoben — der einzige Kaltstart pro Tag ist der Morgen-Start. Jede neue Stufe muss den
  `running`-Guard erben.
- **`_wp_target` wird aus dem *rohen* Register gebootstrappt** (beliebiger Wert 35–75, nicht
  zwingend eine Stufe). Stufen-Vergleiche deshalb **explizit** formulieren, nie per `else`
  auffangen — sonst landet ein Zwischenwert in einem Zweig ohne `running`-Guard und löst
  einen Kaltstart auf Maximum aus.
- **Schwellen werden nirgends gegeneinander validiert** (der Options-Flow hat keine
  Cross-Field-Validierung, die Number-Entities ändern je ein Feld einzeln). `pv.py` klemmt
  sie deshalb beim Einlesen und hat ein Sicherheitsventil (`ladder_reaches_ceiling`), damit
  eine verdrehte Konfiguration den Heizstab nicht dauerhaft aussperrt.
- **Schichtreihenfolge:** Schicht 1 (WP-Stufen) läuft **vor** Schicht 2 (Heizstab), damit
  dessen Deckel-Gate den Stand desselben Zyklus sieht.
- **Entprellung:** ein gemeinsamer `_debounced()`-Mechanismus für alle Stufen; jeder
  Stufenwechsel braucht die volle Entprellzeit.

## Testen

Es gibt **kein** automatisiertes Testsetup; CI fährt nur `hassfest` + HACS-Validierung.
Vor jedem Commit mindestens:

```bash
python -m py_compile custom_components/haier_modbus/*.py
python -c "import json;[json.load(open(f'custom_components/haier_modbus/{f}',encoding='utf-8')) for f in ['manifest.json','strings.json','translations/de.json','translations/en.json']]"
```

Für Regelungsänderungen lohnt eine **Simulation der echten Logik** mit gestubbten
HA-Modulen (`homeassistant.*` als Dummy-Packages in `sys.modules`, `pv.py` per
`importlib` direkt laden, damit das Paket-`__init__` nicht greift). Damit lassen sich
Überschuss-Rampen und Reload-Szenarien durchspielen, ohne HA zu starten — hat mehrere
Fehler vor dem Merge gefunden.

Ist eine Home-Assistant-MCP-Verbindung verfügbar, sind **echte Verlaufsdaten** das beste
Beweismittel für Regelungsfragen (Historie/Statistik der Temperatur-, Modus- und
Status-Entitäten). Erst messen, dann schlussfolgern.

## Git

Entwicklung auf einem `claude/*`-Branch, Draft-PR, CI abwarten, nach Freigabe squash-mergen.
Ist der Branch bereits gemergt, für Folgearbeit **frisch von `main` aufsetzen**
(`git checkout -B <branch> origin/main`), nicht auf gemergter Historie weiterbauen.

> **Symptom, wenn das vergessen wird: die CI startet gar nicht.** Nach einem
> Squash-Merge liegen dieselben Änderungen doppelt vor (einzeln auf dem Branch,
> gesquasht auf `main`) → der PR wird `mergeable_state: "dirty"`, und GitHub führt
> `pull_request`-Workflows nicht aus, weil der Merge-Commit nicht berechenbar ist.
> Es erscheinen **null Check-Runs** – das sieht wie ein CI-Ausfall aus, ist aber ein
> Konflikt. Prüfen mit `pull_request_read method=get` (Feld `mergeable_state`), nicht
> nur mit `get_check_runs`. Reparatur: Branch von `origin/main` neu aufsetzen und die
> eigenen Commits per `git cherry-pick` übertragen.

**HACS zieht Versionen aus GitHub-Releases, nicht aus `main`.** Nach dem Merge ist noch ein
Release mit passendem Tag (`vX.Y.Z`) nötig, sonst bleibt die Integration bei der alten
Version stehen.
