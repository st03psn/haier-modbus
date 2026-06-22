"""DataUpdateCoordinator: ein Block-Read (1..90) je Intervall, plus Schreibzugriff."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from pymodbus.client import AsyncModbusTcpClient

import homeassistant.util.dt as dt_util

from .const import (
    CONF_COP_ELEC_ENTITY,
    CONF_COP_ELEC_SOURCE,
    CONF_COP_HEAT_ENTITY,
    CONF_COP_HEAT_SOURCE,
    CONF_COP_REF_DATE,
    CONF_ENERGY_SCALE,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    DEFAULT_ENERGY_SCALE,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DOMAIN,
    READ_COUNT,
    READ_START,
    REG_AMBIENT,
    REG_HEAT_YEAR,
    REG_HEATER_ELEC_YEAR,
    REG_HP_ELEC_YEAR,
    REG_SET_TEMP,
    SOURCE_EXTERNAL,
)
from .energy import EnergyAccumulator, consumption_since, state_float
from .pv import PvController

_LOGGER = logging.getLogger(__name__)

_SAVE_INTERVAL_S = 300  # Persistenz höchstens alle 5 min


def _signed16(value: int) -> int:
    """int16 vorzeichenbehaftet interpretieren (z. B. Umgebungstemperatur)."""
    return value - 0x10000 if value >= 0x8000 else value


class HaierModbusCoordinator(DataUpdateCoordinator[dict[int, int]]):
    """Hält den Registerzustand und kapselt Lese-/Schreibzugriffe."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        # Verbindungsdaten: Options haben Vorrang (im GUI änderbar), sonst Setup-Daten.
        self.host: str = entry.options.get(CONF_HOST, entry.data[CONF_HOST])
        self.port: int = entry.options.get(
            CONF_PORT, entry.data.get(CONF_PORT, DEFAULT_PORT)
        )
        self.slave: int = entry.options.get(
            CONF_SLAVE, entry.data.get(CONF_SLAVE, DEFAULT_SLAVE)
        )
        scan = entry.options.get(
            CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        self._client = AsyncModbusTcpClient(self.host, port=self.port)
        self.energy = EnergyAccumulator(hass, entry.entry_id)
        self._pv = PvController(hass)
        self._last_save = None
        self._seed_done = False
        # "COP seit Bezugsdatum": Ergebnis + gedrosselter Statistik-Cache
        self.ref_cop: float | None = None
        self.ref_cop_attrs: dict = {}
        self._ref_cache: dict = {}
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
        """Schreibt mit FC 0x10 (Write Multiple Registers).

        Laut Hersteller-Doku unterstützen die RW-Register nur 0x03/0x10 –
        NICHT 0x06 (Write Single Register). FC 0x06 quittiert das Gerät mit
        einer Ausnahme (0x86). Daher write_registers mit einer Ein-Wort-Liste.
        """
        try:
            return await self._client.write_registers(
                address, [value], device_id=self.slave
            )
        except TypeError:
            return await self._client.write_registers(
                address, [value], slave=self.slave
            )

    async def _async_update_data(self) -> dict[int, int]:
        try:
            if not self._client.connected:
                await self._client.connect()
            if not self._client.connected:
                raise UpdateFailed(
                    f"Keine Verbindung zum Modbus-Konverter unter {self.host}:{self.port}"
                )

            rr = await self._read_holding(READ_START, READ_COUNT)
            if rr.isError():
                raise UpdateFailed(f"Modbus-Fehler beim Lesen (Konverter erreichbar?): {rr}")

            regs = rr.registers
            data = {
                addr: regs[addr - READ_START]
                for addr in range(READ_START, READ_START + READ_COUNT)
            }
            if REG_AMBIENT in data:
                data[REG_AMBIENT] = _signed16(data[REG_AMBIENT])

            await self._maybe_seed()
            await self._accumulate_energy(data)
            await self._compute_ref_cop(data)
            await self._pv.async_evaluate(self, data)
            return data
        except UpdateFailed:
            raise
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(str(err)) from err

    async def _maybe_seed(self) -> None:
        """Einmal pro Start die Monats-/Jahres-Eimer aus der Statistik vorbefüllen.

        Quellen entsprechen der COP-Konfiguration: extern -> gewählte Entität,
        Modbus -> die Geräte-„dieses Jahr"-Sensoren (deren reset-bereinigte
        Statistik-``sum`` das korrekte Fenster liefert).
        """
        if self._seed_done:
            return
        self._seed_done = True
        reg = er.async_get(self.hass)

        def eid(key: str) -> str | None:
            return reg.async_get_entity_id("sensor", DOMAIN, f"{self.entry.entry_id}_{key}")

        o = self.entry.options
        if o.get(CONF_COP_HEAT_SOURCE) == SOURCE_EXTERNAL:
            heat_ids = [o[CONF_COP_HEAT_ENTITY]] if o.get(CONF_COP_HEAT_ENTITY) else []
        else:
            h = eid("heat_year")
            heat_ids = [h] if h else []
        if o.get(CONF_COP_ELEC_SOURCE) == SOURCE_EXTERNAL:
            elec_ids = [o[CONF_COP_ELEC_ENTITY]] if o.get(CONF_COP_ELEC_ENTITY) else []
        else:
            elec_ids = [x for x in (eid("hp_elec_year"), eid("heater_elec_year")) if x]

        try:
            await self.energy.async_seed(self.hass, heat_ids, elec_ids)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Statistik-Seeding übersprungen: %s", err)

    async def _ref_stat(self, kind: str, ids: list[str], start, now) -> float | None:
        """Statistik-Verbrauch seit Bezugsdatum – pro Quelle gecacht (alle 5 min)."""
        cache = self._ref_cache.get(kind)
        if cache and cache["start"] == start and (now - cache["ts"]).total_seconds() < 300:
            return cache["value"]
        value = await consumption_since(self.hass, ids, start, now)
        self._ref_cache[kind] = {"ts": now, "start": start, "value": value}
        return value

    async def _compute_ref_cop(self, data: dict[int, int]) -> None:
        """COP seit einem Bezugsdatum (Wärmezähler-Reset).

        Wärme = aktueller Geräte-Zähler (Annahme: am Bezugsdatum genullt) bzw.
        externer Zähler seit Datum; Strom = Verbrauch seit Datum (Statistik bei
        externer Quelle, Geräte-Zähler bei Modbus). Damit decken beide denselben
        Zeitraum ab, ohne dass eine Wärme-Historie nötig ist.
        """
        o = self.entry.options
        ref_str = o.get(CONF_COP_REF_DATE)
        if not ref_str:
            self.ref_cop = None
            self.ref_cop_attrs = {}
            return
        ref_date = dt_util.parse_date(ref_str)
        if ref_date is None:
            self.ref_cop = None
            return

        start = dt_util.start_of_local_day(ref_date)
        now = dt_util.now()
        scale = o.get(CONF_ENERGY_SCALE, DEFAULT_ENERGY_SCALE)

        if o.get(CONF_COP_HEAT_SOURCE) == SOURCE_EXTERNAL:
            heat = await self._ref_stat("heat", [o.get(CONF_COP_HEAT_ENTITY)], start, now)
        else:
            raw = data.get(REG_HEAT_YEAR)
            heat = raw * scale if raw is not None else None

        if o.get(CONF_COP_ELEC_SOURCE) == SOURCE_EXTERNAL:
            elec = await self._ref_stat("elec", [o.get(CONF_COP_ELEC_ENTITY)], start, now)
        else:
            hp = data.get(REG_HP_ELEC_YEAR)
            heater = data.get(REG_HEATER_ELEC_YEAR)
            elec = ((hp or 0) + (heater or 0)) * scale if (hp is not None or heater is not None) else None

        self.ref_cop = round(heat / elec, 2) if (heat and elec) else None
        self.ref_cop_attrs = {
            "reference_date": ref_str,
            "heat_kwh": round(heat, 3) if heat else heat,
            "electricity_kwh": round(elec, 3) if elec else elec,
        }

    async def _accumulate_energy(self, data: dict[int, int]) -> None:
        """Wärme/Strom (quellabhängig) in kalender-ausgerichtete Eimer zählen."""
        if not self.energy.loaded:
            await self.energy.async_load()

        o = self.entry.options
        scale = o.get(CONF_ENERGY_SCALE, DEFAULT_ENERGY_SCALE)

        if o.get(CONF_COP_HEAT_SOURCE) == SOURCE_EXTERNAL:
            heat = state_float(self.hass, o.get(CONF_COP_HEAT_ENTITY))
        else:
            raw = data.get(REG_HEAT_YEAR)
            heat = raw * scale if raw is not None else None

        if o.get(CONF_COP_ELEC_SOURCE) == SOURCE_EXTERNAL:
            elec = state_float(self.hass, o.get(CONF_COP_ELEC_ENTITY))
        else:
            hp = data.get(REG_HP_ELEC_YEAR)
            heater = data.get(REG_HEATER_ELEC_YEAR)
            elec = ((hp or 0) + (heater or 0)) * scale if (hp is not None or heater is not None) else None

        self.energy.update(heat, elec)

        now = dt_util.now()
        if self._last_save is None or (now - self._last_save).total_seconds() >= _SAVE_INTERVAL_S:
            self._last_save = now
            await self.energy.async_save()

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

    async def write_setpoint(self, value: int) -> None:
        """Solltemperatur (Reg 6) setzen – für die interne PV-Steuerung.

        Bewusst ohne anschließenden Refresh-Request (wird ohnehin im selben
        Lesezyklus aufgerufen), um keine Rekursion auszulösen.
        """
        if not self._client.connected:
            await self._client.connect()
        await self._write_holding(REG_SET_TEMP, int(value))

    async def async_close(self) -> None:
        try:
            await self.energy.async_save()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass
