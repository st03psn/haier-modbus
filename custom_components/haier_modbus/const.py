"""Konstanten und Modbus-Registerkarte der Haier Brauchwasserwärmepumpe.

Registerkarte aus der offiziellen Hersteller-Doku
"Haier-Haustechnik.de Brauchwasser-WP MODBUS Einstellung" (Holding-Register, FC 0x03).
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "haier_modbus"

# --- Config-Flow Keys (Einrichtung) ----------------------------------------
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_SLAVE: Final = "slave"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_MODEL: Final = "model"

DEFAULT_PORT: Final = 502
DEFAULT_SLAVE: Final = 1
DEFAULT_SCAN_INTERVAL: Final = 5  # Sekunden

# --- Options-Flow Keys (COP / Energiequellen, alles über die UI) -----------
CONF_COP_ENABLED: Final = "cop_enabled"
CONF_COP_ELEC_SOURCE: Final = "cop_elec_source"   # "modbus" | "external"
CONF_COP_ELEC_ENTITY: Final = "cop_elec_entity"   # externer Stromzähler (kWh)
CONF_COP_HEAT_SOURCE: Final = "cop_heat_source"   # "modbus" | "external"
CONF_COP_HEAT_ENTITY: Final = "cop_heat_entity"   # externer Wärmemengenzähler (kWh)
CONF_ENERGY_SCALE: Final = "energy_scale"         # kWh-Register-Skalierung (1.0 / 0.1 / ...)
CONF_COP_REF_DATE: Final = "cop_ref_date"         # Bezugsdatum (Wärmezähler-Reset) für COP seit Datum

SOURCE_MODBUS: Final = "modbus"
SOURCE_EXTERNAL: Final = "external"

DEFAULT_ENERGY_SCALE: Final = 1.0

# --- PV-Überschuss-Steuerung (optional, in der Integration) -----------------
CONF_PV_ENABLED: Final = "pv_enabled"
CONF_PV_SENSOR: Final = "pv_sensor"            # Sensor PV-Überschuss in W
CONF_PV_HIGH: Final = "pv_high"                # Schwelle hoher Überschuss (W)
CONF_PV_NORMAL: Final = "pv_normal"            # Schwelle normaler Überschuss (W)
CONF_PV_TEMP_HIGH: Final = "pv_temp_high"      # Zieltemp bei hohem Überschuss
CONF_PV_TEMP_NORMAL: Final = "pv_temp_normal"  # Zieltemp bei normalem Überschuss
CONF_PV_TEMP_BASE: Final = "pv_temp_base"      # Grund-Zieltemp ohne Überschuss
CONF_PV_DEBOUNCE: Final = "pv_debounce"        # Entprellzeit (Minuten)

DEFAULT_PV_HIGH: Final = 1500
DEFAULT_PV_NORMAL: Final = 400
DEFAULT_PV_TEMP_HIGH: Final = 70
DEFAULT_PV_TEMP_NORMAL: Final = 65
DEFAULT_PV_TEMP_BASE: Final = 50
DEFAULT_PV_DEBOUNCE: Final = 5

# Gerät
MANUFACTURER: Final = "Haier"
MODEL: Final = "HP200M7-F9"          # Standard-/Fallback-Modell

# Mitgeliefertes Dashboard
DASHBOARD_URL_PATH: Final = "haier-bwwp"
DASHBOARD_TITLE: Final = "Haier BWWP"
DASHBOARD_ICON: Final = "mdi:water-boiler"

# Bekannte Modelle der Haier-BWWP-M7-Familie (gleiche Modbus-Registerkarte).
# Schlüssel slug-konform (hassfest-Anforderung an Selector-Keys) -> Anzeigename.
# Tankvolumen wird bewusst nicht erfasst (am Modell erkennbar). "other" = generisch.
MODELS: Final = {
    "hp160m7_f9": "HP160M7-F9",
    "hp200m7_f9": "HP200M7-F9",
    "hp260m7_f9": "HP260M7-F9",
    "other": "Haier BWWP",
}
DEFAULT_MODEL_KEY: Final = "hp200m7_f9"

# --- Block-Read ------------------------------------------------------------
# Ein Read über Adresse 1..90 (90 Register <= 125 Limit von FC 0x03).
# HINWEIS: pymodbus adressiert PDU-basiert. Falls alle Werte um 1 verschoben
# erscheinen, READ_START / die Adressen unten um 1 anpassen und mit dem
# bisher funktionierenden YAML abgleichen.
READ_START: Final = 1
READ_COUNT: Final = 90

# --- Steuer-/Statusregister (1..18) ---------------------------------------
REG_MODE: Final = 1            # RW  0 AUTO | 1 ECO | 2 ELEC | 3 VAC
REG_FUNCTION: Final = 2       # RW  Bitfeld: bit0 active, bit1 boost, bit2 mute, bit3 sterilize
REG_STATUS: Final = 3         # R   Bitfeld: bit0 WP, bit1 E-Heizstab, bit2 Solar, bit3 Kessel
REG_HOTWATER_PCT: Final = 4   # R   %
REG_TARGET_TEMP: Final = 5    # R   °C (geräteinterne Zieltemperatur)
REG_SET_TEMP: Final = 6       # RW  °C (Sollwert, 35..75)
REG_WATER_TEMP: Final = 7     # R   °C (Ist)
REG_TANK_TOP: Final = 8       # R   °C
REG_TANK_BOTTOM: Final = 9    # R   °C
REG_AMBIENT: Final = 10       # R   °C, vorzeichenbehaftet (int16, -50..100)
# 11..17  RTC (Jahr/Monat/Tag/Woche/Stunde/Minute/Sekunde)
REG_FAULT: Final = 18         # R   Fehlercode 0..64

SET_TEMP_MIN: Final = 35
SET_TEMP_MAX: Final = 75

# --- Energie-/Wärmeregister (kWh) -----------------------------------------
# Jeder Block: 7 Tageswerte + 12 Monatswerte + 5 Jahreswerte.
# "dieses Jahr" = letztes Register des jeweiligen Blocks.
REG_HP_ELEC_YEAR: Final = 42        # Kompressor-/WP-Strom, dieses Jahr
REG_HEATER_ELEC_YEAR: Final = 66    # Heizstab-Strom, dieses Jahr
REG_HEAT_YEAR: Final = 90           # akkumulierte Wärmemenge, dieses Jahr

# Monatsarrays (Jan..Dez) – Startadressen, je 12 Register
REG_HP_ELEC_MONTHS: Final = 26      # 26..37
REG_HEATER_ELEC_MONTHS: Final = 50  # 50..61
REG_HEAT_MONTHS: Final = 74         # 74..85

# --- Mode-Mapping ----------------------------------------------------------
MODE_AUTO: Final = 0
MODE_ECO: Final = 1
MODE_ELEC: Final = 2
MODE_VAC: Final = 3
MODE_TO_TEXT: Final = {MODE_AUTO: "AUTO", MODE_ECO: "ECO", MODE_ELEC: "ELEC", MODE_VAC: "VAC"}
TEXT_TO_MODE: Final = {v: k for k, v in MODE_TO_TEXT.items()}

# --- Funktionsregister-Bits (Reg 2) ---------------------------------------
BIT_ACTIVE: Final = 1 << 0
BIT_BOOST: Final = 1 << 1
BIT_MUTE: Final = 1 << 2
BIT_STERILIZE: Final = 1 << 3

# --- Statusregister-Bits (Reg 3) ------------------------------------------
STATUS_HEATPUMP: Final = 1 << 0
STATUS_EHEATER: Final = 1 << 1
STATUS_SOLAR: Final = 1 << 2
STATUS_BOILER: Final = 1 << 3

PLATFORMS: Final = [
    "water_heater",
    "sensor",
    "number",
    "select",
    "switch",
    "binary_sensor",
]
