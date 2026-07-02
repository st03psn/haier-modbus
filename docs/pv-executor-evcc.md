# PV-Modus „Executor" — Anbindung an ein HEMS (Beispiel: evcc)

Im **Executor-Modus** regelt die Integration nicht selbst, sondern stellt die
Programm-Entität `select.haier_hwhp_pv_program` bereit
(`aus` / `grund` / `ueberschuss` / `boost`); ein externes HEMS setzt sie, die
Integration übersetzt das Programm in Sollwert/Modus/Boost. Grundlagen und
Effizienz-Strategie: siehe README, Abschnitt „PV-Überschuss — Betriebsmodi".

## Brücke evcc → Home Assistant

evcc kennt die Wärmepumpe nicht nativ. Robusteste Brücke: evcc liefert seinen
Überschuss/Status per MQTT an HA, eine **HA-Automation** mappt das auf das
Programm-Select — **nicht** direkt per Modbus schreiben (kein zweiter
Bus-Master):

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

## Hinweise

- Voraussetzung: **PV-Modus = Executor** (sonst regelt der Coordinator gegen).
- Alternativ kann das HEMS den Sollwert direkt setzen (`number.set_value` auf
  `number.haier_hwhp_set_temp`), wenn es die Temperaturen selbst bestimmen
  will — Hoch- und Tief-Ebene nicht mischen.
- Als Status liest das HEMS z. B. `sensor.haier_hwhp_water_temp`,
  `binary_sensor.haier_hwhp_status_wp`, die Leistungsaufnahme (externer
  Zähler, z. B. Shelly) und `sensor.haier_hwhp_set_temp`.
- Der **38-°C-Guard** bleibt als lokales Sicherheitsnetz aktiv (separater
  Haken, greift am Modus, nicht am Sollwert).
