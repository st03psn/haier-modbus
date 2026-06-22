"""DataUpdateCoordinator: ein Block-Read (1..90) je Intervall, plus Schreibzugriff."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    REG_HEAT_MONTHS,
    REG_HEAT_YEAR,
    REG_HEATER_ELEC_MONTHS,
    REG_HEATER_ELEC_YEAR,
    REG_HP_ELEC_MONTHS,
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

            await self._maybe_seed(data)
            await self._accumulate_energy(data)
            await self._compute_ref_cop(data)
            await self._pv.async_evaluate(self, data)
            return data
        except UpdateFailed:
            raise
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(str(err)) from err

    def _ref_date(self, data: dict[int, int]):
        """(Bezugsdatum, Signatur) – manuelles Override oder Auto-Erkennung.

        Manuelles ``cop_ref_date`` (Options) hat Vorrang; sonst erster Monat des
        Jahres mit Wärme. Die Signatur dient dem Re-Seed-Erkennen bei Änderung.
        """
        ref_str = self.entry.options.get(CONF_COP_REF_DATE)
        if ref_str:
            d = dt_util.parse_date(ref_str)
            return d, (ref_str if d else None)
        d = self._auto_ref_date(data)
        return d, (f"auto:{d.isoformat()}" if d else None)

    async def _maybe_seed(self, data: dict[int, int]) -> None:
        """Monats-/Jahres-/Gesamt-Eimer seeden; Re-Seed bei Versions- oder
        Bezugsdatum-Wechsel.

        Strom-Fenster richten sich nach dem Bezugsdatum (Beginn =
        max(Kalenderbeginn, Bezugsdatum)) – so wird der Strom *vor* dem ersten
        Wärmewert nicht mitgezählt. Wärme: Modbus -> Geräteregister, extern ->
        Statistik. Externe Statistik noch nicht da -> nächster Zyklus.
        """
        if self._seed_done:
            return
        if not self.energy.loaded:
            await self.energy.async_load()

        ref_date, ref_sig = self._ref_date(data)
        if not self.energy.needs_seed and self.energy.seed_ref == ref_sig:
            self._seed_done = True
            return

        o = self.entry.options
        scale = o.get(CONF_ENERGY_SCALE, DEFAULT_ENERGY_SCALE)
        now = dt_util.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        m = now.month - 1  # 0..11 -> Offset in die Monatsarrays
        ref_start = dt_util.start_of_local_day(ref_date) if ref_date else None
        m_start = max(month_start, ref_start) if ref_start else month_start
        y_start = max(year_start, ref_start) if ref_start else year_start

        if o.get(CONF_COP_HEAT_SOURCE) == SOURCE_EXTERNAL:
            ent = o.get(CONF_COP_HEAT_ENTITY)
            mh = await consumption_since(self.hass, [ent], m_start, now)
            yh = await consumption_since(self.hass, [ent], y_start, now)
        else:
            mh = (data.get(REG_HEAT_MONTHS + m) or 0) * scale
            yh = (data.get(REG_HEAT_YEAR) or 0) * scale

        if o.get(CONF_COP_ELEC_SOURCE) == SOURCE_EXTERNAL:
            ent = o.get(CONF_COP_ELEC_ENTITY)
            me = await consumption_since(self.hass, [ent], m_start, now)
            ye = await consumption_since(self.hass, [ent], y_start, now)
        else:
            me = (
                (data.get(REG_HP_ELEC_MONTHS + m) or 0)
                + (data.get(REG_HEATER_ELEC_MONTHS + m) or 0)
            ) * scale
            ye = (
                (data.get(REG_HP_ELEC_YEAR) or 0)
                + (data.get(REG_HEATER_ELEC_YEAR) or 0)
            ) * scale

        if None in (mh, me, yh, ye):
            return  # externe Statistik noch nicht verfügbar -> nächster Zyklus

        # Das Jahr umfasst den Monat -> physikalische Untergrenze erzwingen.
        yh = max(yh, mh)
        ye = max(ye, me)

        # Gesamt-Werte = „seit Bezugsdatum" (vergleichbar Wärme/Strom).
        total_heat = yh
        if o.get(CONF_COP_ELEC_SOURCE) == SOURCE_EXTERNAL and ref_start is not None:
            total_elec = await consumption_since(
                self.hass, [o.get(CONF_COP_ELEC_ENTITY)], ref_start, now
            )
            if total_elec is None:
                total_elec = me
        else:
            total_elec = ye
        total_elec = max(total_elec, me)

        try:
            await self.energy.async_seed(mh, me, yh, ye, total_heat, total_elec, ref_sig)
            self._seed_done = True
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Seeding übersprungen: %s", err)

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
        auto = False
        if ref_str:
            ref_date = dt_util.parse_date(ref_str)
        else:
            ref_date = self._auto_ref_date(data)
            auto = True
        if ref_date is None:
            self.ref_cop = None
            self.ref_cop_attrs = {}
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
            "reference_date": ref_date.isoformat(),
            "reference_auto": auto,
            "heat_kwh": round(heat, 3) if heat else heat,
            "electricity_kwh": round(elec, 3) if elec else elec,
        }

    def _auto_ref_date(self, data: dict[int, int]) -> date | None:
        """Bezugsdatum automatisch: erster Monat des laufenden Jahres mit Wärme > 0.

        Nutzt die Monats-Wärmewerte des Geräts (Reg 74..85 = Jan..Dez), die im
        Block-Read ohnehin mitkommen. Fällt auf den Jahresanfang zurück, wenn die
        Monatswerte leer sind, aber „dieses Jahr" Wärme zeigt.
        """
        now = dt_util.now()
        for k in range(12):  # Jan..Dez -> Reg 74..85
            v = data.get(REG_HEAT_MONTHS + k)
            if v and v > 0:
                return date(now.year, k + 1, 1)
        raw = data.get(REG_HEAT_YEAR)
        if raw and raw > 0:
            return date(now.year, 1, 1)
        return None

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
