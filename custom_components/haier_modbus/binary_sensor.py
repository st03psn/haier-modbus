"""Binärsensoren: Betriebsstatus-Bits (Register 3) + Verbindung."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    REG_STATUS,
    STATUS_BOILER,
    STATUS_EHEATER,
    STATUS_HEATPUMP,
    STATUS_SOLAR,
)
from .entity import HaierModbusEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            HaierStatusBit(coordinator, "wp", STATUS_HEATPUMP, "mdi:heat-pump"),
            HaierStatusBit(coordinator, "heater", STATUS_EHEATER, "mdi:radiator"),
            # Solar/Kessel = optionale externe Quellen (Heizregister im Speicher).
            # Geräte ohne diesen Anschluss zeigen sie nie -> standardmäßig deaktiviert.
            HaierStatusBit(coordinator, "solar", STATUS_SOLAR, "mdi:solar-power",
                           enabled_default=False),
            HaierStatusBit(coordinator, "boiler", STATUS_BOILER, "mdi:water-boiler",
                           enabled_default=False),
            HaierConnection(coordinator),
        ]
    )


class HaierStatusBit(HaierModbusEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator, key: str, bitmask: int, icon: str,
                 enabled_default: bool = True) -> None:
        super().__init__(coordinator)
        self._bitmask = bitmask
        self._attr_translation_key = f"status_{key}"
        self._attr_icon = icon
        self._attr_unique_id = f"{coordinator.entry.entry_id}_status_{key}"
        self._attr_entity_registry_enabled_default = enabled_default

    @property
    def is_on(self) -> bool | None:
        raw = self._regs.get(REG_STATUS)
        return None if raw is None else bool(raw & self._bitmask)


class HaierConnection(HaierModbusEntity, BinarySensorEntity):
    # C3: ``_attr_entity_category = None`` war ein No-op (das ist ohnehin der
    # Default) - CONNECTIVITY gehört per HA-Konvention nach DIAGNOSTIC, analog
    # ``sensor.link_status``, das dasselbe beschreibt.
    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_connection"

    @property
    def is_on(self) -> bool:
        # Spiegelt den echten Modbus-Linkstatus (nicht nur die Daten-Karenzzeit).
        return self.coordinator.link_status == "ok"

    @property
    def available(self) -> bool:
        return True
