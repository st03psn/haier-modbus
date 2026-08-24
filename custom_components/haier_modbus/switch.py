"""Switches: einzelne Bits im Funktionsregister (Register 2, RW) + PV-Option als
Bedien-Fassade (v1.16.5, analog zu ``HaierPvOptionNumber`` in ``number.py``).

Wichtig: Ein Schreibzugriff auf die Options-Fassade löst **keinen** Integration-Reload
aus – der Update-Listener überspringt die Keys aus ``LIVE_OPTION_KEYS`` bewusst (siehe
``__init__.py``), weil ``pv.py`` sie ohnehin bei jedem Poll frisch liest.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BIT_ACTIVE,
    BIT_BOOST,
    BIT_MUTE,
    BIT_STERILIZE,
    CONF_EMERGENCY_ENABLED,
    CONF_LEGIONELLA_ENABLED,
    CONF_PV_BOOST_ONLY_NEGATIVE_PRICE,
    CONF_PV_MODE,
    CONF_PV_MORNING_ENABLED,
    DEFAULT_PV_BOOST_ONLY_NEGATIVE_PRICE,
    DEFAULT_PV_MORNING_ENABLED,
    DOMAIN,
    PV_MODE_COORDINATOR,
    REG_FUNCTION,
)
from .entity import HaierModbusEntity


@dataclass(frozen=True, kw_only=True)
class OptionSwitch:
    """Beschreibung einer Switch-Fassade auf einen bool-Options-Schlüssel."""

    key: str
    default: bool
    icon: str | None = None


# Notheizung/Legionellen-Watchdog: unabhängig vom PV-Modus, unconditional angelegt.
EMERGENCY_LEGIONELLA_SWITCHES: tuple[OptionSwitch, ...] = (
    OptionSwitch(key=CONF_EMERGENCY_ENABLED, default=False, icon="mdi:thermometer-alert"),
    OptionSwitch(key=CONF_LEGIONELLA_ENABLED, default=False, icon="mdi:bacteria-outline"),
)

# Morgen-Start an/aus: nur im Coordinator-Modus relevant (der Executor überlässt den
# Tagesplan dem HEMS).
PV_COORDINATOR_SWITCHES: tuple[OptionSwitch, ...] = (
    OptionSwitch(key=CONF_PV_MORNING_ENABLED, default=DEFAULT_PV_MORNING_ENABLED,
                 icon="mdi:weather-sunset-up"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = [
        HaierBitSwitch(coordinator, "active", BIT_ACTIVE, "mdi:power"),
        HaierBitSwitch(coordinator, "boost", BIT_BOOST, "mdi:rocket-launch"),
        HaierBitSwitch(coordinator, "mute", BIT_MUTE, "mdi:volume-mute"),
        HaierBitSwitch(coordinator, "sterilize", BIT_STERILIZE, "mdi:bacteria"),
    ]
    entities += [HaierOptionSwitch(coordinator, d) for d in EMERGENCY_LEGIONELLA_SWITCHES]
    # Nur im Coordinator-Modus relevant – der Executor überlässt Boost/Preis-Logik
    # dem externen HEMS (gleicher Split wie die PV-Number-Entities).
    if entry.options.get(CONF_PV_MODE) == PV_MODE_COORDINATOR:
        entities.append(HaierPvBoostOnlyNegativePriceSwitch(coordinator))
        entities += [HaierOptionSwitch(coordinator, d) for d in PV_COORDINATOR_SWITCHES]
    async_add_entities(entities)


class HaierBitSwitch(HaierModbusEntity, SwitchEntity):
    """Setzt/löscht ein Bit im Funktionsregister."""

    def __init__(self, coordinator, key: str, bitmask: int, icon: str) -> None:
        super().__init__(coordinator)
        self._bitmask = bitmask
        self._attr_translation_key = key
        self._attr_icon = icon
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"

    @property
    def is_on(self) -> bool | None:
        raw = self._regs.get(REG_FUNCTION)
        return None if raw is None else bool(raw & self._bitmask)

    async def async_turn_on(self, **kwargs) -> None:
        # W9: ohne bislang erfolgreichen Block-Read ist ``REG_FUNCTION`` unbekannt -
        # ein Fallback auf 0 würde beim Schreiben ALLE fremden Bits löschen
        # (BIT_ACTIVE/BIT_MUTE/BIT_STERILIZE), das Gerät ginge aus. Vorlage:
        # ``pv._apply_heater`` verweigert unter derselben Bedingung ebenfalls.
        current = self._regs.get(REG_FUNCTION)
        if current is None:
            raise HomeAssistantError(
                "Funktionsregister noch nicht gelesen - Schalten aktuell nicht möglich"
            )
        await self.coordinator.async_write_register(REG_FUNCTION, current | self._bitmask)

    async def async_turn_off(self, **kwargs) -> None:
        current = self._regs.get(REG_FUNCTION)
        if current is None:
            raise HomeAssistantError(
                "Funktionsregister noch nicht gelesen - Schalten aktuell nicht möglich"
            )
        await self.coordinator.async_write_register(REG_FUNCTION, current & ~self._bitmask)


class HaierPvBoostOnlyNegativePriceSwitch(HaierModbusEntity, SwitchEntity):
    """Bedien-Fassade auf ``pv_boost_only_negative_price`` in ``entry.options``.

    Ohne konfigurierten Negativpreis-Sensor (``pv_negative_price_sensor``) bleibt der
    Schalter wirkungslos – ``pv.py`` wertet das Gate nur aus, wenn beides gesetzt ist
    (s. Modul-Docstring dort). Kein Fehler, nur ein Hinweis für den Nutzer.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "pv_boost_only_negative_price"
    _attr_icon = "mdi:currency-eur-off"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_pv_boost_only_negative_price"

    @property
    def available(self) -> bool:
        """Config-Entity: auch bei Modbus-Störung einsehbar/änderbar."""
        return True

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.entry.options.get(
            CONF_PV_BOOST_ONLY_NEGATIVE_PRICE, DEFAULT_PV_BOOST_ONLY_NEGATIVE_PRICE
        )

    async def _set(self, value: bool) -> None:
        entry = self.coordinator.entry
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_PV_BOOST_ONLY_NEGATIVE_PRICE: value}
        )
        # Ohne Reload bleibt diese Entität bestehen -> Zustand selbst nachziehen.
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)


class HaierOptionSwitch(HaierModbusEntity, SwitchEntity):
    """Generische Bedien-Fassade auf einen bool-Options-Schlüssel (Notheizung/
    Legionellen-Watchdog/Morgen-Start an-aus) – Muster analog
    ``HaierPvBoostOnlyNegativePriceSwitch``, hier parametrisiert statt je
    Option eine eigene Klasse.
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, desc: OptionSwitch) -> None:
        super().__init__(coordinator)
        self._desc = desc
        self._attr_translation_key = desc.key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{desc.key}"
        self._attr_icon = desc.icon

    @property
    def available(self) -> bool:
        """Config-Entity: auch bei Modbus-Störung einsehbar/änderbar."""
        return True

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.entry.options.get(self._desc.key, self._desc.default)

    async def _set(self, value: bool) -> None:
        entry = self.coordinator.entry
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, self._desc.key: value}
        )
        # Ohne Reload bleibt diese Entität bestehen -> Zustand selbst nachziehen.
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
