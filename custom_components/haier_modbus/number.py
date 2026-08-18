"""Number: Solltemperatur (Register 6, RW) + PV-Schwellen als Config-Entities.

Die PV-Schwellen/Zieltemperaturen liegen weiterhin **allein** in ``entry.options``
(eine Quelle der Wahrheit, identisch mit dem „Konfigurieren"-Dialog) – diese Entitäten
sind nur eine Bedien-/Sicht-Fassade darauf, damit die Werte direkt auf der Geräteseite
einsehbar und änderbar sind, ohne durch den mehrstufigen Options-Dialog zu müssen.

Wichtig: Ein Schreibzugriff löst **keinen** Integration-Reload aus – der Update-Listener
überspringt die Keys aus ``LIVE_OPTION_KEYS`` bewusst (siehe ``__init__.py``), weil
``pv.py`` sie ohnehin bei jedem Poll frisch liest und ein Reload interne Besitzstände
(Boost-Bit, ELEC-Rückschaltung, manueller Sollwert-Schutz) verwerfen würde.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_PV_COLDSTART,
    CONF_PV_COLDSTART_DELTA,
    CONF_PV_HIGH,
    CONF_PV_HOLD,
    CONF_PV_MAX_STARTS,
    CONF_PV_MIN_RUN,
    CONF_PV_MODE,
    CONF_PV_TEMP_BASE,
    CONF_PV_TEMP_HIGH,
    CONF_PV_TEMP_NORMAL,
    DEFAULT_PV_COLDSTART,
    DEFAULT_PV_COLDSTART_DELTA,
    DEFAULT_PV_HIGH,
    DEFAULT_PV_HOLD,
    DEFAULT_PV_MAX_STARTS,
    DEFAULT_PV_MIN_RUN,
    DEFAULT_PV_TEMP_BASE,
    DEFAULT_PV_TEMP_HIGH,
    DEFAULT_PV_TEMP_NORMAL,
    DOMAIN,
    PV_MODE_COORDINATOR,
    PV_MODE_EXECUTOR,
    REG_SET_TEMP,
    SET_TEMP_MAX,
    SET_TEMP_MIN,
    WP_MAX_TEMP,
)
from .entity import HaierModbusEntity


@dataclass(frozen=True, kw_only=True)
class OptionNumber:
    """Beschreibung einer Number-Fassade auf einen Options-Schlüssel."""

    key: str
    default: float
    min_value: float
    max_value: float
    step: float = 1
    unit: str | None = None
    icon: str | None = None


# Zieltemperaturen: auch im **Executor**-Modus wirksam – das Programm-Select
# (select.py) übersetzt seine Programme über genau diese Werte in Sollwerte.
# Normal/Erhöht muss der **Verdichter allein** schaffen -> auf WP_MAX_TEMP begrenzt.
# S. docs/geraete-grenzen.md
PV_TEMP_NUMBERS: tuple[OptionNumber, ...] = (
    OptionNumber(key=CONF_PV_TEMP_BASE, default=DEFAULT_PV_TEMP_BASE,
                 min_value=SET_TEMP_MIN, max_value=WP_MAX_TEMP,
                 unit=UnitOfTemperature.CELSIUS, icon="mdi:thermometer-low"),
    OptionNumber(key=CONF_PV_TEMP_NORMAL, default=DEFAULT_PV_TEMP_NORMAL,
                 min_value=SET_TEMP_MIN, max_value=WP_MAX_TEMP,
                 unit=UnitOfTemperature.CELSIUS, icon="mdi:thermometer"),
)

# Boost-Zieltemperatur: seit v1.16.0 nur noch für das Executor-Programm relevant
# (``select.PV_PROGRAM_BOOST``) – im Coordinator-Modus ist Boost eine Leistungssenke
# und nutzt dieselbe Zieltemperatur wie Erhöht (AP2). Daher hier bewusst NICHT mehr im
# Coordinator-Modus angezeigt (sonst ein wirkungsloses Bedienelement).
PV_TEMP_HIGH_NUMBER = OptionNumber(
    key=CONF_PV_TEMP_HIGH, default=DEFAULT_PV_TEMP_HIGH,
    min_value=SET_TEMP_MIN, max_value=SET_TEMP_MAX,
    unit=UnitOfTemperature.CELSIUS, icon="mdi:thermometer-high",
)

# Watt-Schwellen: nur im **Coordinator**-Modus relevant (gleicher Split wie im
# Options-Dialog, wo sie ebenfalls nur für Coordinator angeboten werden).
PV_WATT_NUMBERS: tuple[OptionNumber, ...] = (
    OptionNumber(key=CONF_PV_HOLD, default=DEFAULT_PV_HOLD,
                 min_value=0, max_value=10000, step=50, unit="W", icon="mdi:solar-power"),
    OptionNumber(key=CONF_PV_HIGH, default=DEFAULT_PV_HIGH,
                 min_value=0, max_value=10000, step=50, unit="W", icon="mdi:radiator"),
)

# Tagesplan-Kennzahlen (v1.16.4): Kaltstart-Schwelle/-Defizit, Tageskontingent,
# Mindestlaufzeit. Nur im **Coordinator**-Modus relevant – der Executor überlässt den
# Tagesplan dem HEMS. Bewusst als eigene Entities (statt nur im Options-Dialog), weil
# sie im Betrieb erfahrungsgemäß häufiger nachjustiert werden als die Basiswerte.
# Grenzen identisch zu den Selectors im Options-Flow (config_flow.py: _WATT/_KELVIN/
# _STARTS/_MINUTES), damit beide Wege dieselben Werte zulassen.
PV_TAGESPLAN_NUMBERS: tuple[OptionNumber, ...] = (
    OptionNumber(key=CONF_PV_COLDSTART, default=DEFAULT_PV_COLDSTART,
                 min_value=0, max_value=10000, step=50, unit="W", icon="mdi:weather-sunny"),
    OptionNumber(key=CONF_PV_COLDSTART_DELTA, default=DEFAULT_PV_COLDSTART_DELTA,
                 min_value=0, max_value=30, step=1, unit="K", icon="mdi:thermometer-minus"),
    OptionNumber(key=CONF_PV_MAX_STARTS, default=DEFAULT_PV_MAX_STARTS,
                 min_value=1, max_value=5, step=1, icon="mdi:counter"),
    OptionNumber(key=CONF_PV_MIN_RUN, default=DEFAULT_PV_MIN_RUN,
                 min_value=1, max_value=180, step=1, unit="min", icon="mdi:timer-play-outline"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[NumberEntity] = [HaierSetTemperature(coordinator)]

    mode = entry.options.get(CONF_PV_MODE)
    if mode in (PV_MODE_COORDINATOR, PV_MODE_EXECUTOR):
        entities += [HaierPvOptionNumber(coordinator, d) for d in PV_TEMP_NUMBERS]
    if mode == PV_MODE_EXECUTOR:
        entities.append(HaierPvOptionNumber(coordinator, PV_TEMP_HIGH_NUMBER))
    if mode == PV_MODE_COORDINATOR:
        entities += [HaierPvOptionNumber(coordinator, d) for d in PV_WATT_NUMBERS]
        entities += [HaierPvOptionNumber(coordinator, d) for d in PV_TAGESPLAN_NUMBERS]

    async_add_entities(entities)


class HaierSetTemperature(HaierModbusEntity, NumberEntity):
    _attr_translation_key = "set_temp"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = SET_TEMP_MIN
    _attr_native_max_value = SET_TEMP_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:thermometer-water"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_set_temp"

    @property
    def native_value(self) -> float | None:
        return self._regs.get(REG_SET_TEMP)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write_register(REG_SET_TEMP, int(value))


class HaierPvOptionNumber(HaierModbusEntity, NumberEntity):
    """Bedien-Fassade auf einen PV-Schwellenwert in ``entry.options``.

    Bewusst ``NumberMode.BOX`` statt SLIDER: Ein Slider-Zug würde bei jedem
    Zwischenschritt schreiben; die Box schreibt einmal beim Bestätigen.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, desc: OptionNumber) -> None:
        super().__init__(coordinator)
        self._desc = desc
        self._attr_translation_key = desc.key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{desc.key}"
        self._attr_native_min_value = desc.min_value
        self._attr_native_max_value = desc.max_value
        self._attr_native_step = desc.step
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_icon = desc.icon

    @property
    def available(self) -> bool:
        """Config-Entity: auch bei Modbus-Störung einsehbar/änderbar."""
        return True

    @property
    def native_value(self) -> float | None:
        return self.coordinator.entry.options.get(self._desc.key, self._desc.default)

    async def async_set_native_value(self, value: float) -> None:
        entry = self.coordinator.entry
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, self._desc.key: value}
        )
        # Ohne Reload bleibt diese Entität bestehen -> Zustand selbst nachziehen.
        self.async_write_ha_state()
