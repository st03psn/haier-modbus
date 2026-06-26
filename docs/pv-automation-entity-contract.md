# Entity Contract: PV-Surplus Automation

Dieses Dokument beschreibt den Entitäts-Vertrag zwischen der `haier_modbus`-Integration
und der mitgelieferten PV-Überschuss-Automation
(`blueprints/automation/haier_modbus/pv_surplus.yaml`).

> Funktionsweise, Schwellen & Tuning des Blueprints: [`pv-surplus-blueprint.md`](pv-surplus-blueprint.md).

**Ziel:** Releases sollen diese Entities nicht still umbenennen oder beschneiden —
genau das hat die Vorgänger-Automationen getötet (frühere Schemata: `haier_brauchwasserwarmepumpe_*`, `hk29_bwwp_*`).

---

## Entities, die stabil bleiben müssen

### Schreib-Ziel

| Entity | Dienst | Wertebereich | Modbus |
|---|---|---|---|
| `number.haier_hwhp_set_temp` | `number.set_value` | 35–75 °C (Step 1) | Register 0x10, schreibend |

**Kritisch:** `number.set_value` muss schreibend durchgehen. Modbus-Refactors dürfen
dieses Register nicht stillschweigend auf read-only stellen oder den Typ auf `sensor`
ändern.

### Lesende Entities (Integrations-seitig)

| Entity | Verwendung |
|---|---|
| `sensor.haier_hwhp_water_temp` | Speicher-Temperatur-Guard vor Hochsetzen |
| `binary_sensor.haier_hwhp_status_wp` | Verdichter-Laufstatus (on = läuft) |

### Externe Inputs (nicht Teil der Integration)

| Entity | Bedeutung |
|---|---|
| `sensor.pv_uberschuss_watt` | PV-Überschuss in Watt (user-seitig, z. B. Shelly/Fronius) |
| `sensor.shelly_hz_bwwp_power` | Aktueller BWWP-Stromverbrauch (dynamische Normalschwelle) |

Die externen Entities sind user-konfigurierbar im Blueprint — sie gehören **nicht**
zur Integration, müssen aber als `device_class: power` vorliegen.

---

## Stabilität der `entity_id`

Das aktuelle config-entry-basierte Namensschema (`haier_hwhp_*`) ist gut.
**Bitte bei Umbenennungen eine HA-Migration mitliefern** (`entity_registry` rename via
`config_entries`/`entity_registry_updated`), damit bestehende Automationen nicht
stillschweigend auf `unavailable` gehen.

Historischer Hintergrund: Die Entitäten hießen in früheren Versionen
`haier_brauchwasserwarmepumpe_*` bzw. `hk29_bwwp_*`. Jede Umbenennung hat alle
aufgebauten Automationen der Nutzer invalidiert.

---

## Empfehlung: Blueprint zusammen mit Integration ausliefern

Die Automation ist bereits als Blueprint unter
`blueprints/automation/haier_modbus/pv_surplus.yaml` verpackt.
Bei einem künftigen Breaking-Change an den Entity-IDs:

1. Blueprint-Version bumpen und `min_ha_version` setzen.
2. Alte Entity-IDs per Migration im Integration-Code umbenennen.
3. Blueprint-Changelog dokumentieren, welche Inputs sich geändert haben.

So bleibt die Kopplung explizit und übersteht Updates ohne manuelle Nutzer-Eingriffe.

---

## Kurzcheckliste vor jedem Release

- [ ] `number.haier_hwhp_set_temp` schreibt noch via `number.set_value` (Modbus 0x10)?
- [ ] `sensor.haier_hwhp_water_temp` und `binary_sensor.haier_hwhp_status_wp` haben
      dieselbe `entity_id` wie bisher?
- [ ] Falls Entity-ID-Änderung unvermeidbar: Migration im Code + Blueprint-Version bump?
