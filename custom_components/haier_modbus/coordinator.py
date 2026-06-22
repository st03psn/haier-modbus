"""DataUpdateCoordinator: ein Block-Read (1..90) je Intervall, plus Schreibzugriff."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from pymodbus.client import AsyncModbusTcpClient

from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DOMAIN,
    READ_COUNT,
    READ_START,
    REG_AMBIENT,
)

_LOGGER = logging.getLogger(__name__)


def _signed16(value: int) -> int:
    """int16 vorzeichenbehaftet interpretieren (z. B. Umgebungstemperatur)."""
    return value - 0x10000 if value >= 0x8000 else value


class HaierModbusCoordinator(DataUpdateCoordinator[dict[int, int]]):
    """Hält den Registerzustand und kapselt Lese-/Schreibzugriffe."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.host: str = entry.data[CONF_HOST]
        self.port: int = entry.data.get(CONF_PORT, DEFAULT_PORT)
        self.slave: int = entry.data.get(CONF_SLAVE, DEFAULT_SLAVE)
        scan = entry.options.get(
            CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        self._client = AsyncModbusTcpClient(self.host, port=self.port)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan),
        )

    async def _read_holding(self, address: int, count: int):
        """pymodbus benannte slave->device_id um ~3.9; beide Wege unterstützen."""
        try:
            return await self._client.read_holding_registers(
                address, count=count, device_id=self.slave
            )
        except TypeError:
            return await self._client.read_holding_registers(
                address, count=count, slave=self.slave
            )

    async def _write_holding(self, address: int, value: int):
        try:
            return await self._client.write_register(
                address, value, device_id=self.slave
            )
        except TypeError:
            return await self._client.write_register(address, value, slave=self.slave)

    async def _async_update_data(self) -> dict[int, int]:
        try:
            if not self._client.connected:
                await self._client.connect()
            if not self._client.connected:
                raise UpdateFailed(f"Keine Verbindung zu {self.host}:{self.port}")

            rr = await self._read_holding(READ_START, READ_COUNT)
            if rr.isError():
                raise UpdateFailed(f"Modbus-Fehler beim Lesen: {rr}")

            regs = rr.registers
            data = {
                addr: regs[addr - READ_START]
                for addr in range(READ_START, READ_START + READ_COUNT)
            }
            if REG_AMBIENT in data:
                data[REG_AMBIENT] = _signed16(data[REG_AMBIENT])
            return data
        except UpdateFailed:
            raise
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(str(err)) from err

    async def async_write_register(self, address: int, value: int) -> None:
        """Einzelregister schreiben und danach sofort aktualisieren."""
        try:
            if not self._client.connected:
                await self._client.connect()
            resp = await self._write_holding(address, int(value))
            if resp.isError():
                raise UpdateFailed(f"Schreibfehler an {address}: {resp}")
        finally:
            await self.async_request_refresh()

    async def async_close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass
