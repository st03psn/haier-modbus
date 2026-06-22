"""Sensoren: Temperaturen, Status, Energie und berechneter COP."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_COP_ELEC_ENTITY,
    CONF_COP_ELEC_SOURCE,
    CONF_COP_ENABLED,
    CONF_COP_HEAT_ENTITY,
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
    REG_TANK_BOTTOM,
    REG_TANK_TOP,
    REG_TARGET_TEMP,
    REG_WATER_TEMP,
    SOURCE_EXTERNAL,
)
from .entity import HaierModbusEntity


@dataclass(frozen=True, kw_only=True)
class RegSensor:
    key: str
    name: str
    register: int
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    icon: str | None = None
    factor: float = 1.0


TEMP_SENSORS: tuple[RegSensor, ...] = (
    RegSensor(key="water_temp", name="Wassertemperatur", register=REG_WATER_TEMP,
              unit=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE,
              state_class=SensorStateClass.MEASUREMENT),
    RegSensor(key="target_temp", name="Zieltemperatur", register=REG_TARGET_TEMP,
              unit=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE,
              state_class=SensorStateClass.MEASUREMENT),
    RegSensor(key="tank_top", name="Tank oben", register=REG_TANK_TOP,
              unit=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE,
              state_class=SensorStateClass.MEASUREMENT),
    RegSensor(key="tank_bottom", name="Tank unten", register=REG_TANK_BOTTOM,
              unit=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE,
              state_class=SensorStateClass.MEASUREMENT),
    RegSensor(key="ambient", name="Umgebungstemperatur", register=REG_AMBIENT,
              unit=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE,
              state_class=SensorStateClass.MEASUREMENT),
    RegSensor(key="hotwater_pct", name="Warmwasserstand", register=REG_HOTWATER_PCT,
              unit=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT, icon="mdi:water-percent"),
    RegSensor(key="fault", name="Fehlercode", register=REG_FAULT, icon="mdi:alert-circle-outline"),
)

ENERGY_SENSORS: tuple[RegSensor, ...] = (
    RegSensor(key="hp_elec_year", name="WP-Strom (dieses Jahr)", register=REG_HP_ELEC_YEAR,
              unit=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY,
              state_class=SensorStateClass.TOTAL_INCREASING),
    RegSensor(key="heater_elec_year", name="Heizstab-Strom (dieses Jahr)", register=REG_HEATER_ELEC_YEAR,
              unit=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY,
              state_class=SensorStateClass.TOTAL_INCREASING),
    RegSensor(key="heat_year", name="Wärmemenge (dieses Jahr)", register=REG_HEAT_YEAR,
              unit=UnitOfEnergy.KILO_WATT_HOUR, device_class=SensorDeviceClass.ENERGY,
              state_class=SensorStateClass.TOTAL_INCREASING),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [HaierRegSensor(coordinator, d) for d in TEMP_SENSORS]
    entities.append(HaierModeText(coordinator))
    entities += [HaierEnergySensor(coordinator, entry, d) for d in ENERGY_SENSORS]
    entities.append(HaierCopSensor(coordinator, entry))
    async_add_entities(entities)


def _scale(entry: ConfigEntry) -> float:
    return entry.options.get(CONF_ENERGY_SCALE, DEFAULT_ENERGY_SCALE)


def _state_float(hass: HomeAssistant, entity_id: str | None) -> float | None:
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", "", None):
        return None
    try:
        return float(state.state)
    except (ValueError, TypeError):
        return None


class HaierRegSensor(HaierModbusEntity, SensorEntity):
    def __init__(self, coordinator, desc: RegSensor) -> None:
        super().__init__(coordinator)
        self._desc = desc
        self._attr_name = desc.name
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
        return raw * self._desc.factor if self._desc.factor != 1.0 else raw


class HaierModeText(HaierModbusEntity, SensorEntity):
    _attr_name = "Modus (Text)"
    _attr_icon = "mdi:tune-variant"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_mode_text"

    @property
    def native_value(self):
        return MODE_TO_TEXT.get(self._regs.get(REG_MODE, -1))


class HaierEnergySensor(HaierModbusEntity, SensorEntity):
    """kWh-Register mit konfigurierbarer Skalierung."""

    def __init__(self, coordinator, entry: ConfigEntry, desc: RegSensor) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._desc = desc
        self._attr_name = desc.name
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


class HaierCopSensor(HaierModbusEntity, SensorEntity):
    """COP (laufendes Jahr) = Wärmemenge / eingesetzter Strom.

    Quellen frei wählbar (Options-Flow):
      - Wärme:  Modbus-Register 90  ODER externer Wärmemengenzähler
      - Strom:  Modbus (42 + 66)    ODER externer Stromzähler (z. B. Shelly)

    Hinweis: Bei externer Stromquelle sollte ein *jährlich zurücksetzender*
    Zähler (utility_meter, cycle: yearly) gewählt werden, damit das Fenster
    zur geräteseitigen Jahres-Wärmemenge passt.
    """

    _attr_name = "COP (dieses Jahr)"
    _attr_icon = "mdi:gauge"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{coordinator.entry.entry_id}_cop_year"

    @property
    def native_value(self):
        o = self._entry.options
        if not o.get(CONF_COP_ENABLED, True):
            return None
        scale = _scale(self._entry)

        # Wärme
        if o.get(CONF_COP_HEAT_SOURCE) == SOURCE_EXTERNAL:
            heat = _state_float(self.hass, o.get(CONF_COP_HEAT_ENTITY))
        else:
            raw = self._regs.get(REG_HEAT_YEAR)
            heat = raw * scale if raw is not None else None

        # Strom
        if o.get(CONF_COP_ELEC_SOURCE) == SOURCE_EXTERNAL:
            elec = _state_float(self.hass, o.get(CONF_COP_ELEC_ENTITY))
        else:
            hp = self._regs.get(REG_HP_ELEC_YEAR)
            heater = self._regs.get(REG_HEATER_ELEC_YEAR)
            if hp is None and heater is None:
                elec = None
            else:
                elec = ((hp or 0) + (heater or 0)) * scale

        if not heat or not elec:
            return None
        return round(heat / elec, 2)

    @property
    def extra_state_attributes(self):
        o = self._entry.options
        return {
            "heat_source": o.get(CONF_COP_HEAT_SOURCE, "modbus"),
            "electricity_source": o.get(CONF_COP_ELEC_SOURCE, "modbus"),
            "energy_scale": _scale(self._entry),
        }
