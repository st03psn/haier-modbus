"""Sensoren: Temperaturen, Status, Energie und berechneter COP."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_AMBIENT_OFFSET,
    CONF_COP_ELEC_SOURCE,
    CONF_COP_ENABLED,
    CONF_COP_HEAT_SOURCE,
    CONF_ENERGY_SCALE,
    DEFAULT_ENERGY_SCALE,
    DOMAIN,
    MODE_TO_TEXT,
    REG_AMBIENT,
    REG_FAULT,
    REG_HEAT_YEAR,
    REG_HEATER_ELEC_YEAR,
    REG_HOTWATER_PCT,
    REG_HP_ELEC_YEAR,
    REG_MODE,
    REG_STATUS,
    REG_TANK_BOTTOM,
    REG_TANK_TOP,
    REG_TARGET_TEMP,
    REG_WATER_TEMP,
    STATUS_BOILER,
    STATUS_EHEATER,
    STATUS_HEATPUMP,
    STATUS_SOLAR,
)
from .entity import HaierModbusEntity


@dataclass(frozen=True, kw_only=True)
class RegSensor:
    key: str
    register: int
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    icon: str | None = None
    factor: float = 1.0
    offset_key: str | None = None   # Options-Key eines additiven Korrektur-Offsets


TEMP_SENSORS: tuple[RegSensor, ...] = (
    RegSensor(key="water_temp", register=REG_WATER_TEMP,
              unit=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE,
              state_class=SensorStateClass.MEASUREMENT),
    RegSensor(key="target_temp", register=REG_TARGET_TEMP,
              unit=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE,
              state_class=SensorStateClass.MEASUREMENT),
    RegSensor(key="tank_top", register=REG_TANK_TOP,
              unit=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE,
              state_class=SensorStateClass.MEASUREMENT),
    RegSensor(key="tank_bottom", register=REG_TANK_BOTTOM,
              unit=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE,
              state_class=SensorStateClass.MEASUREMENT),
    RegSensor(key="ambient", register=REG_AMBIENT,
              unit=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE,
              state_class=SensorStateClass.MEASUREMENT, offset_key=CONF_AMBIENT_OFFSET),
    RegSensor(key="hotwater_pct", register=REG_HOTWATER_PCT,
              unit=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, icon="mdi:water-percent"),
    RegSensor(key="fault", register=REG_FAULT, icon="mdi:alert-circle-outline"),
)

ENERGY_SENSORS: tuple[RegSensor, ...] = (
    RegSensor(key="hp_elec_year", register=REG_HP_ELEC_YEAR,
              unit=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY,
              state_class=SensorStateClass.TOTAL_INCREASING),
    RegSensor(key="heater_elec_year", register=REG_HEATER_ELEC_YEAR,
              unit=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY,
              state_class=SensorStateClass.TOTAL_INCREASING),
    RegSensor(key="heat_year", register=REG_HEAT_YEAR,
              unit=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY,
              state_class=SensorStateClass.TOTAL_INCREASING),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [HaierRegSensor(coordinator, d) for d in TEMP_SENSORS]
    entities.append(HaierModeText(coordinator))
    entities.append(HaierCurrentSource(coordinator))
    entities += [HaierEnergySensor(coordinator, entry, d) for d in ENERGY_SENSORS]
    entities.append(HaierAccEnergy(coordinator, "total_heat", "heat_total"))
    entities.append(HaierAccEnergy(coordinator, "total_elec", "elec_total"))
    entities.append(HaierCopSensor(coordinator, entry, "month"))
    entities.append(HaierCopSensor(coordinator, entry, "year"))
    entities.append(HaierPrevYearCop(coordinator))
    entities.append(HaierLinkStatus(coordinator))
    async_add_entities(entities)


class HaierLinkStatus(HaierModbusEntity, SensorEntity):
    """Modbus-Verbindungsstatus: ok / Konverter nicht erreichbar / Gerät stumm.

    Eigener Grundtest je Zyklus (TCP zum Konverter vs. RTU-Antwort des Geräts).
    Bleibt bewusst immer verfügbar – auch wenn die Datenentitäten (nach Ablauf
    der Karenzzeit) auf „nicht verfügbar" gehen.
    """

    _attr_translation_key = "link_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ok", "no_converter", "no_device"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:lan-connect"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_link_status"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return self.coordinator.link_status


# Reg-3-Bits -> (Schlüssel, Reihenfolge = Anzeigereihenfolge).
_SOURCE_BITS: tuple[tuple[int, str], ...] = (
    (STATUS_HEATPUMP, "heat_pump"),
    (STATUS_SOLAR, "solar"),
    (STATUS_BOILER, "boiler"),
    (STATUS_EHEATER, "electric_heater"),
)

# Klartext-Labels je Quelle, zweisprachig (DE für deutsche HA-Instanz, sonst EN).
# Direkt im Code, weil HA-State-Übersetzung keine "WP + Heizstab"-Kombis kann.
_SOURCE_LABELS: dict[str, dict[str, str]] = {
    "de": {
        "idle": "Aus",
        "heat_pump": "Wärmepumpe",
        "solar": "Solar",
        "boiler": "Kessel",
        "electric_heater": "Heizstab",
    },
    "en": {
        "idle": "Off",
        "heat_pump": "Heat pump",
        "solar": "Solar",
        "boiler": "Boiler",
        "electric_heater": "Electric heater",
    },
}


def _scale(entry: ConfigEntry) -> float:
    return entry.options.get(CONF_ENERGY_SCALE, DEFAULT_ENERGY_SCALE)


class HaierRegSensor(HaierModbusEntity, SensorEntity):
    def __init__(self, coordinator, desc: RegSensor) -> None:
        super().__init__(coordinator)
        self._desc = desc
        self._attr_translation_key = desc.key
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_device_class = desc.device_class
        self._attr_state_class = desc.state_class
        self._attr_icon = desc.icon
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{desc.key}"

    @property
    def native_value(self):
        raw = self._regs.get(self._desc.register)
        if raw is None:
            return None
        val = raw * self._desc.factor if self._desc.factor != 1.0 else raw
        if self._desc.offset_key:
            offset = self.coordinator.entry.options.get(self._desc.offset_key, 0.0)
            if offset:
                val = round(val + offset, 1)
        return val


class HaierModeText(HaierModbusEntity, SensorEntity):
    """Aktueller Modus als Text (read-only, Reg 1)."""

    _attr_translation_key = "mode_text"
    _attr_icon = "mdi:tune-variant"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_mode_text"

    @property
    def native_value(self):
        return MODE_TO_TEXT.get(self._regs.get(REG_MODE, -1))


class HaierCurrentSource(HaierModbusEntity, SensorEntity):
    """Aktuell genutzte Erzeugerquelle(n) aus dem Betriebsstatus (Reg 3).

    Mehrere Bits können gleichzeitig aktiv sein (z. B. WP + Heizstab); dann
    werden alle aktiven Quellen aufgelistet. Keine aktive Quelle -> "idle".
    Der Rohwert (Bitmaske) und die Liste der aktiven Keys stehen in den
    Attributen, damit Automationen sprachunabhängig darauf zugreifen können.
    """

    _attr_translation_key = "current_source"
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_current_source"

    def _active_keys(self) -> list[str] | None:
        raw = self._regs.get(REG_STATUS)
        if raw is None:
            return None
        return [key for bit, key in _SOURCE_BITS if raw & bit]

    @property
    def native_value(self) -> str | None:
        keys = self._active_keys()
        if keys is None:
            return None
        lang = (self.hass.config.language or "en").split("-")[0]
        labels = _SOURCE_LABELS.get(lang, _SOURCE_LABELS["en"])
        if not keys:
            return labels["idle"]
        return " + ".join(labels.get(k, k) for k in keys)

    @property
    def extra_state_attributes(self):
        keys = self._active_keys()
        raw = self._regs.get(REG_STATUS)
        return {
            "active_sources": keys or [],
            "status_register": raw,
        }


class HaierEnergySensor(HaierModbusEntity, SensorEntity):
    """kWh-Register mit konfigurierbarer Skalierung."""

    def __init__(self, coordinator, entry: ConfigEntry, desc: RegSensor) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._desc = desc
        self._attr_translation_key = desc.key
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_device_class = desc.device_class
        self._attr_state_class = desc.state_class
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{desc.key}"

    @property
    def native_value(self):
        raw = self._regs.get(self._desc.register)
        if raw is None:
            return None
        return round(raw * _scale(self._entry), 3)


class HaierAccEnergy(HaierModbusEntity, SensorEntity):
    """Monoton akkumulierte Gesamt-Energie (kWh) – speist das Energie-Dashboard.

    Im Gegensatz zu den geräteseitigen „dieses Jahr"-Registern (die zu eigenen
    Zeitpunkten resetten) zählt dieser Wert über HA-kontrollierte positive
    Deltas nur aufwärts – ideal als ``total_increasing`` für Verbrauchs-/
    Erzeugungskurven mit automatischer Tages-/Monats-/Jahres-Aufschlüsselung.
    """

    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, key: str, translation_key: str) -> None:
        super().__init__(coordinator)
        self._key = key  # 'total_heat' | 'total_elec'
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"

    @property
    def native_value(self):
        return self.coordinator.energy.value(self._key)


class HaierCopSensor(HaierModbusEntity, SensorEntity):
    """COP über ein kalender-ausgerichtetes Fenster: Monat oder Jahr (JAZ).

    Quelle ist der interne Energie-Akkumulator: Wärme und Strom werden in HA in
    gemeinsamen Monats-/Jahres-Eimern gezählt – beide also immer über dasselbe
    Fenster, unabhängig davon, wann ein Geräteregister intern zurückgesetzt
    wird. Strom-/Wärmequelle bleiben im Setup/Options-Flow wählbar.
    """

    _attr_icon = "mdi:gauge"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, entry: ConfigEntry, period: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._period = period  # 'month' | 'year'
        self._attr_translation_key = "cop_month" if period == "month" else "cop_year"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_cop_{period}"

    @property
    def native_value(self):
        if not self._entry.options.get(CONF_COP_ENABLED, True):
            return None
        return self.coordinator.energy.cop(self._period)

    @property
    def extra_state_attributes(self):
        o = self._entry.options
        e = self.coordinator.energy
        attrs = {
            "heat_source": o.get(CONF_COP_HEAT_SOURCE, "modbus"),
            "electricity_source": o.get(CONF_COP_ELEC_SOURCE, "modbus"),
            "heat_kwh": e.value(f"{self._period}_heat"),
            "electricity_kwh": e.value(f"{self._period}_elec"),
        }
        if self._period == "year":
            # Abgeschlossene Jahre für den Jahr-zu-Jahr-Vergleich (z. B. ApexCharts).
            attrs["jaz_per_year"] = e.history()
        else:
            # Abgeschlossene Monate für den Monat-zu-Monat-Vergleich.
            attrs["cop_per_month"] = e.month_history()
        return attrs


class HaierPrevYearCop(HaierModbusEntity, SensorEntity):
    """JAZ des zuletzt abgeschlossenen Jahres (für den Jahresvergleich).

    Wird beim Jahreswechsel aus dem dann abgeschlossenen Jahr gesetzt; die
    vollständige Jahresliste steht als Attribut der JAZ-(Jahr-)Entität.
    """

    _attr_translation_key = "cop_prev_year"
    _attr_icon = "mdi:gauge"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_cop_prev_year"

    @property
    def native_value(self):
        return self.coordinator.energy.previous_year_cop()

    @property
    def extra_state_attributes(self):
        return {"jaz_per_year": self.coordinator.energy.history()}
