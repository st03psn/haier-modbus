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
# Quelle ergibt sich aus der Entität: leer = Modbus-Register, gesetzt = extern.
CONF_COP_ELEC_ENTITY: Final = "cop_elec_entity"   # externer Stromzähler (kWh); leer = Modbus
CONF_COP_HEAT_ENTITY: Final = "cop_heat_entity"   # externer Wärmemengenzähler (kWh); leer = Modbus
# Legacy (nur noch für die einmalige Options-Migration in __init__.py):
CONF_COP_ELEC_SOURCE: Final = "cop_elec_source"   # alt: "modbus" | "external"
CONF_COP_HEAT_SOURCE: Final = "cop_heat_source"   # alt: "modbus" | "external"
CONF_ENERGY_SCALE: Final = "energy_scale"         # kWh-Register-Skalierung (1.0 / 0.1 / ...)
CONF_COP_REF_DATE: Final = "cop_ref_date"         # Bezugsdatum (Wärmezähler-Reset) für COP seit Datum
CONF_AMBIENT_OFFSET: Final = "ambient_offset"     # Korrektur-Offset für die Umgebungstemperatur (°C)

DEFAULT_AMBIENT_OFFSET: Final = 0.0

SOURCE_MODBUS: Final = "modbus"
SOURCE_EXTERNAL: Final = "external"

DEFAULT_ENERGY_SCALE: Final = 1.0

# --- PV-Überschuss-Steuerung (optional, in der Integration) -----------------
# Betriebsmodus (Dropdown, ersetzt den alten Bool-Haken "PV-Überschuss aktiv"):
#  - off          : pv.py inert; nur die rohen Stell-Entitäten + 38°-Guard.
#  - coordinator  : die Integration regelt selbst nach Roh-Überschuss + Morgen-Start.
#  - executor     : externes HEMS regelt; die Integration stellt nur die Programme
#                   bereit (select.haier_hwhp_pv_program), pv.py regelt NICHT.
CONF_PV_MODE: Final = "pv_mode"
PV_MODE_OFF: Final = "off"
PV_MODE_COORDINATOR: Final = "coordinator"
PV_MODE_EXECUTOR: Final = "executor"
DEFAULT_PV_MODE: Final = PV_MODE_OFF

CONF_PV_SENSOR: Final = "pv_sensor"            # Sensor PV-Überschuss in W (roh, ≥0)
CONF_PV_HIGH: Final = "pv_high"                # Boost-Schwelle Roh-Überschuss (W) -> Heizstab-Schicht
CONF_PV_HOLD: Final = "pv_hold"                # Halte-/Piggyback-Puffer: darüber WP-Zyklus halten (W)
CONF_PV_SOLAR_BOOST: Final = "pv_solar_boost"  # Solar-Boost-Schwelle (W): WP klettert allein auf die Boost-Zieltemp
# Optionaler Sensor (binary_sensor/input_boolean), der die aktuelle Viertelstunde als
# Negativ-/Null-Preis markiert (Solarspitzengesetz/§51 EEG). Ist er an, entfällt der
# Effizienz-Vorteil des Wartens -> der Heizstab darf schon vor dem Deckel zuschalten.
CONF_PV_NEGATIVE_PRICE_SENSOR: Final = "pv_negative_price_sensor"
CONF_PV_MORNING_ENABLED: Final = "pv_morning_enabled"      # fixer Morgen-Start aktiv (bool)
CONF_PV_MORNING_TIME: Final = "pv_morning_time"            # Uhrzeit Morgen-Start ("HH:MM")
CONF_PV_TEMP_HIGH: Final = "pv_temp_high"      # Boost-Zieltemp (bei hohem Überschuss)
CONF_PV_TEMP_NORMAL: Final = "pv_temp_normal"  # Erhöht-Zieltemp (bei normalem Überschuss)
CONF_PV_TEMP_BASE: Final = "pv_temp_base"      # Normal-Zieltemp (ohne Überschuss)
CONF_PV_DEBOUNCE: Final = "pv_debounce"        # Entprellzeit (Minuten)
CONF_PV_MIN_OFF: Final = "pv_min_off"          # Anti-Takt: Mindest-Stillstand vor Neustart (min)
# Eskalation bei hohem Überschuss – gegenseitig ausschließend (ein Dropdown):
CONF_PV_ESCALATION: Final = "pv_escalation"    # "none" | "boost" | "elec"
PV_ESC_NONE: Final = "none"
PV_ESC_BOOST: Final = "boost"                  # Boost: WP + Heizstab gleichzeitig
PV_ESC_ELEC: Final = "elec"                    # ELEC: nur Heizstab, WP aus
DEFAULT_PV_ESCALATION: Final = PV_ESC_NONE

# Executor: Regelprogramme, die ein HEMS (oder der Nutzer) setzt; die Integration
# übersetzt das Programm idempotent in die Mechanik (Sollwert/Modus/Boost).
CONF_PV_PROGRAM: Final = "pv_program"
PV_PROGRAM_OFF: Final = "aus"                  # Integration fasst den Sollwert nicht an
PV_PROGRAM_GRUND: Final = "grund"              # Sollwert = 50 °C, Modus ECO
PV_PROGRAM_UEBERSCHUSS: Final = "ueberschuss"  # Sollwert = 65 °C, Modus AUTO
PV_PROGRAM_BOOST: Final = "boost"              # Sollwert = 75 °C + Boost (WP+Heizstab)

# Legacy (nur noch für die einmalige Options-Migration in __init__.py):
CONF_PV_ENABLED: Final = "pv_enabled"          # alt: bool, "PV-Überschuss-Steuerung aktiv"
CONF_PV_BOOST: Final = "pv_boost"              # alt: bool, "zusätzlich Boost"
CONF_PV_FORCE_ELEC: Final = "pv_force_elec"    # alt: bool, "Modus ELEC"

DEFAULT_PV_HOLD: Final = 50
DEFAULT_PV_MORNING_ENABLED: Final = True
DEFAULT_PV_MORNING_TIME: Final = "10:00"
DEFAULT_PV_MIN_OFF: Final = 30

# --- Notfall-Nachheizung (ECO -> AUTO bei kritisch niedriger Temperatur) ----
CONF_EMERGENCY_ENABLED: Final = "emergency_enabled"
CONF_EMERGENCY_CRITICAL: Final = "emergency_critical"   # °C: darunter ECO->AUTO
CONF_EMERGENCY_RECOVER: Final = "emergency_recover"     # °C: darüber zurück AUTO->ECO
DEFAULT_EMERGENCY_CRITICAL: Final = 38
DEFAULT_EMERGENCY_RECOVER: Final = 48

# --- Legionellen-Schutz (periodische thermische Desinfektion) --------------
# Watchdog: erreicht der Speicher nicht innerhalb des Intervalls am Boden
# (Reg 9) die Zieltemperatur, wird ein Desinfektionslauf erzwungen.
CONF_LEGIONELLA_ENABLED: Final = "legionella_enabled"
CONF_LEGIONELLA_INTERVAL: Final = "legionella_interval_days"    # max. Tage zwischen Volldurchheizungen
CONF_LEGIONELLA_TARGET: Final = "legionella_target"            # °C Sollwert für den Desinfektionslauf
CONF_LEGIONELLA_BOTTOM: Final = "legionella_bottom_min"        # °C: ab Tank-unten gilt der Lauf als erreicht
CONF_LEGIONELLA_HOLD: Final = "legionella_hold_min"            # min: so lange muss Tank-unten das Ziel halten
CONF_LEGIONELLA_WINDOW_START: Final = "legionella_window_start"  # bevorzugtes ECO-Fenster (Start "HH:MM")
CONF_LEGIONELLA_WINDOW_END: Final = "legionella_window_end"      # bevorzugtes ECO-Fenster (Ende "HH:MM")

DEFAULT_LEGIONELLA_INTERVAL: Final = 7
DEFAULT_LEGIONELLA_TARGET: Final = 65
DEFAULT_LEGIONELLA_BOTTOM: Final = 60
DEFAULT_LEGIONELLA_HOLD: Final = 30
DEFAULT_LEGIONELLA_WINDOW_START: Final = "10:00"
DEFAULT_LEGIONELLA_WINDOW_END: Final = "18:00"

# Schwellen auf den *rohen* PV-Überschuss (sensor.pv_uberschuss_watt, kappt bei 0):
#  - Halte/Piggyback 50 W = kleiner Puffer; solange noch Überschuss da ist, WP-Zyklus
#    halten/auf Erhöht verlängern (die WP läuft eh schon, kostet keine Extra-Leistung)
#  - Solar-Boost 600 W = die WP klettert allein (ohne Heizstab) bis auf die
#    Boost-Zieltemperatur. Kein spezifizierter Wert – die Modbus-Schnittstelle liefert
#    keine Momentanleistung; am besten am externen Zähler (Shelly) den typischen
#    Verdichter-Verbrauch ablesen und knapp darüber setzen.
#  - Boost 1550 W = Heizstab-Schwelle (Heizstab ~1500 W + Puffer); mehr wird nie gezogen
DEFAULT_PV_HIGH: Final = 1550
DEFAULT_PV_SOLAR_BOOST: Final = 600
DEFAULT_PV_TEMP_HIGH: Final = 75    # Geräte-Max (Reg 6, 35..75); Boost-Stufe = Überschuss verheizen, i. d. R. mit Boost
DEFAULT_PV_TEMP_NORMAL: Final = 65
DEFAULT_PV_TEMP_BASE: Final = 50
DEFAULT_PV_DEBOUNCE: Final = 5

# Options, die ``pv.py`` bei JEDEM Poll frisch aus ``entry.options`` liest. Eine
# Änderung braucht daher KEINEN Integration-Reload – im Gegenteil: ein Reload würde
# In-Memory-Besitzstände verwerfen (Boost-Bit-/ELEC-Ownership in pv.py, manueller
# Sollwert-Schutz, Notheizung, laufender Legionellen-Lauf) und den Heizstab bzw. den
# ELEC-Modus dauerhaft anlassen. Siehe ``_async_update_listener`` in __init__.py.
LIVE_OPTION_KEYS: Final = frozenset({
    CONF_PV_TEMP_BASE,
    CONF_PV_TEMP_NORMAL,
    CONF_PV_TEMP_HIGH,
    CONF_PV_HOLD,
    CONF_PV_SOLAR_BOOST,
    CONF_PV_HIGH,
})

# Gerät
MANUFACTURER: Final = "Haier"
MODEL: Final = "HP200M7-F9"          # Standard-/Fallback-Modell

# Anzeigename nach Systemsprache: Deutsch -> "Haier BWWP"
# (Brauchwasserwärmepumpe), alle anderen Sprachen -> Fallback Englisch
# "Haier HWHP" (Hot Water Heat Pump). Zentral, damit alle Ebenen (Gerät,
# Eintrag, Dashboard, Hinweise) konsistent benannt sind.
TITLE_DE: Final = "Haier BWWP"
TITLE_EN: Final = "Haier HWHP"


def localized_title(language: str | None) -> str:
    """Sprachabhängiger Anzeigename (DE = BWWP, sonst Fallback EN = HWHP)."""
    lang = (language or "en").split("-")[0].lower()
    return TITLE_DE if lang == "de" else TITLE_EN


# Mitgeliefertes Dashboard (Storage-Modus = im UI editierbar)
DASHBOARD_URL_PATH: Final = "haier-hwhp"
DASHBOARD_LEGACY_URL_PATH: Final = "haier-bwwp"  # altes, gesperrtes YAML-Dashboard
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

# --- Fehlercodes -----------------------------------------------------------
# Reg 18 liefert eine Zahl, die laut Modbus-Doku gruppenweise auf Anzeige-Codes
# abbildet: 0 = keiner; 1–15 = E1–EF; 16–31 = L0–LF; 32–47 = F0–FF;
# 48–63 = P0–PF; 64 = PP (Buchstabengruppe + Hex-Ziffer). fault_code() rechnet
# die Zahl in den Anzeige-Code um, FAULT_CODES liefert den Klartext dazu.
FAULT_CODES: Final = {
    "F2": "Verdichterschutz: Betriebstemperatur",
    "F3": "Verdichterschutz: Abluft-Temperatur",
    "F5": "Verdichterschutz: Verdampfer-Übertemperatur",
    "E1": "Stromableitung: zu niedrige elektrische Isolation",
    "E2": "Übertemperatur: Wassertemperatur ≥ 88 °C",
    "E3": "Tank-Temperaturfühler: Kurzschluss/Unterbrechung",
    "E4": "Umgebungs-Temperaturfühler: Kurzschluss/Unterbrechung",
    "E5": "Verdampfer-Temperaturfühler: Kurzschluss/Unterbrechung",
    "E6": "Verdichter-Abluft-Temperaturfühler: Kurzschluss/Unterbrechung",
    "ED": "Verdichter-Ansaug-Temperaturfühler: Kurzschluss/Unterbrechung",
    "E7": "Kommunikationsfehler Hauptplatine ↔ Anzeige",
    "E9": "Umgebungstemperatur-Schutz: < -7 °C oder > 43 °C",
    "EF": "Off-Peak-Signal nicht empfangen",
    "E8": "Druckschalter-Schutz (Auslass)",
    "LB": "Externer Wärmequellen-Temperaturfühler: Kurzschluss/Unterbrechung",
    "L7": "Lüfterfehler: blockiert oder Kommunikationsfehler",
    "F0": "WiFi-Kommunikationsfehler (Konfig-Modus)",
    "P1": "Umrichter: Phasenstrom Hardware-Überstrom",
    "P2": "Umrichter: Phasenstrom Software-Überstrom",
    "P3": "Umrichter: IPM-Temperaturanomalie",
    "P4": "Umrichter: Überlast",
    "P5": "Umrichter: Unterspannungsschutz",
    "P6": "Umrichter: Überspannungsschutz",
    "P7": "Kommunikation Hauptsteuerung ↔ Treiber",
    "P8": "Umrichter: Stromerkennungsschaltung fehlerhaft",
    "PB": "Schrittverlust-Erkennung (out of step)",
    "PD": "Gleichrichter: Software-Überstrom",
    "PF": "Gleichrichter: Hardware-Überstrom",
}


def fault_code(value: int | None) -> str | None:
    """Rohwert von Reg 18 in den Anzeige-Code umrechnen (None = kein Fehler).

    Gruppen laut Modbus-Doku: 1–15 E.., 16–31 L.., 32–47 F.., 48–63 P..,
    64 PP – jeweils Buchstabe + Hex-Ziffer (z. B. 34 -> F2, 27 -> LB, 59 -> PB).
    """
    if value is None or value == 0:
        return None
    if value == 64:
        return "PP"
    if 1 <= value <= 15:               # E-Gruppe: E1..EF (ohne 0)
        return f"E{value:X}"
    for base, letter in ((16, "L"), (32, "F"), (48, "P")):   # L0..LF / F0..FF / P0..PF
        if base <= value <= base + 15:
            return f"{letter}{value - base:X}"
    return None

PLATFORMS: Final = [
    "water_heater",
    "sensor",
    "number",
    "select",
    "switch",
    "binary_sensor",
]
