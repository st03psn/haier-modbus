"""DataUpdateCoordinator: ein Block-Read (1..90) je Intervall, plus Schreibzugriff."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from pymodbus.client import AsyncModbusTcpClient

import homeassistant.util.dt as dt_util

from .const import (
    CONF_COP_ELEC_ENTITY,
    CONF_COP_HEAT_ENTITY,
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
    REG_STATUS,
    STATUS_BOILER,
    STATUS_SOLAR,
)
from .emergency import EmergencyController
from .energy import EnergyAccumulator, consumption_since, state_float
from .legionella import LegionellaController
from .pv import PvController

_LOGGER = logging.getLogger(__name__)

_SAVE_INTERVAL_S = 300  # Persistenz höchstens alle 5 min
_READ_ATTEMPTS = 3       # Lese-Versuche je Zyklus (gegen Konverter-Blips)
_READ_RETRY_DELAY_S = 1  # Pause zwischen den Versuchen
_GRACE_S = 300           # bis zu 5 min letzte Werte halten, bevor "nicht verfügbar"

LINK_OK = "ok"
LINK_NO_CONVERTER = "no_converter"   # TCP zum Konverter nicht erreichbar
LINK_NO_DEVICE = "no_device"         # Konverter erreichbar, aber Gerät (RTU) antwortet nicht


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
        # retries=1 + timeout=3: der Coordinator hat eine eigene Retry-Schleife
        # (mit Reconnect) in _read_block. Sonst würde pymodbus darunter nochmal
        # bis zu 3× retryen (≈9 Versuche/Zyklus) und genau die redundante
        # 'No response received after 3 retries'-ERROR-Zeile erzeugen.
        self._client = AsyncModbusTcpClient(
            self.host, port=self.port, timeout=3, retries=1
        )
        self.energy = EnergyAccumulator(hass, entry.entry_id)
        self.pv = PvController(hass)
        self.legionella = LegionellaController(hass)
        self._emergency = EmergencyController(hass)
        self._last_save = None
        self._seed_done = False
        self.link_status: str = LINK_OK   # ok | no_converter | no_device
        self._fail_since: float | None = None
        self._auto_enabled: set[str] = set()  # Solar/Kessel bei erster Aktivität freigeschaltet
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

    async def _read_block(self) -> dict[int, int]:
        """Block-Read mit mehreren Versuchen + Reconnect.

        Wackelige RTU↔TCP-Konverter liefern gelegentlich Timeouts/Fehler. Statt
        bei einem einzelnen Blip sofort „nicht verfügbar" zu melden (Flapping im
        Logbuch, Lücken im Graphen), wird kurz erneut verbunden und gelesen.
        """
        last_err: Exception | None = None
        reached_converter = False
        for attempt in range(_READ_ATTEMPTS):
            try:
                if not self._client.connected:
                    await self._client.connect()
                if not self._client.connected:
                    raise UpdateFailed(
                        f"Keine Verbindung zum Modbus-Konverter unter {self.host}:{self.port}"
                    )
                reached_converter = True  # TCP zum Konverter steht
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
                self.link_status = LINK_OK
                return data
            except Exception as err:  # noqa: BLE001
                last_err = err
                try:
                    self._client.close()  # Reconnect beim nächsten Versuch erzwingen
                except Exception:  # noqa: BLE001
                    pass
                if attempt < _READ_ATTEMPTS - 1:
                    await asyncio.sleep(_READ_RETRY_DELAY_S)
        # Diagnose: Konverter erreichbar (TCP ok), aber Gerät stumm -> no_device;
        # gar keine TCP-Verbindung -> no_converter.
        self.link_status = LINK_NO_DEVICE if reached_converter else LINK_NO_CONVERTER
        raise (
            last_err
            if isinstance(last_err, UpdateFailed)
            else UpdateFailed(f"Modbus-Lesefehler: {last_err}")
        )

    def _auto_enable_sources(self, data: dict[int, int]) -> None:
        """Solar/Kessel-Sensoren freischalten, sobald die Quelle erstmals aktiv ist.

        Es gibt kein Capability-Register; ein gesetztes Statusbit beweist aber,
        dass die Quelle real vorhanden ist. Standardmäßig sind diese Sensoren
        deaktiviert – hier werden (nur von der Integration deaktivierte) einmalig
        aktiviert. Eine manuelle Nutzer-Deaktivierung bleibt unangetastet.
        """
        raw = data.get(REG_STATUS)
        if raw is None:
            return
        reg = None
        for key, bit in (("solar", STATUS_SOLAR), ("boiler", STATUS_BOILER)):
            if key in self._auto_enabled or not (raw & bit):
                continue
            if reg is None:
                reg = er.async_get(self.hass)
            ent_id = reg.async_get_entity_id(
                "binary_sensor", DOMAIN, f"{self.entry.entry_id}_status_{key}"
            )
            if ent_id:
                ent = reg.async_get(ent_id)
                if ent is not None and ent.disabled_by == er.RegistryEntryDisabler.INTEGRATION:
                    reg.async_update_entity(ent_id, disabled_by=None)
                    _LOGGER.info("Quelle '%s' erstmals aktiv -> Sensor aktiviert", key)
            self._auto_enabled.add(key)

    async def _async_update_data(self) -> dict[int, int]:
        try:
            data = await self._read_block()
            self._fail_since = None
            self._auto_enable_sources(data)
            await self._maybe_seed(data)
            await self._accumulate_energy(data)
            # Legionellen-Schutz zuerst: hat er einen Lauf aktiv, besitzt er
            # Sollwert/Modus und PV/Notheizung treten zurück.
            await self.legionella.async_evaluate(self, data)
            await self.pv.async_evaluate(self, data)
            await self._emergency.async_evaluate(self, data)
            return data
        except UpdateFailed:
            # Kurze Modbus-Aussetzer: letzte Werte bis zu _GRACE_S halten, statt
            # alle Entitäten sofort auf "nicht verfügbar" zu setzen. Der echte
            # Verbindungszustand steht im Sensor "Modbus-Status" (link_status).
            now = self.hass.loop.time()
            if self._fail_since is None:
                self._fail_since = now
            if self.data is not None and (now - self._fail_since) < _GRACE_S:
                _LOGGER.debug(
                    "Modbus-Aussetzer (%s) – halte letzte Werte (%.0fs)",
                    self.link_status,
                    now - self._fail_since,
                )
                return self.data
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

        if o.get(CONF_COP_HEAT_ENTITY):
            ent = o.get(CONF_COP_HEAT_ENTITY)
            mh = await consumption_since(self.hass, [ent], m_start, now)
            yh = await consumption_since(self.hass, [ent], y_start, now)
        else:
            mh = (data.get(REG_HEAT_MONTHS + m) or 0) * scale
            yh = (data.get(REG_HEAT_YEAR) or 0) * scale

        if o.get(CONF_COP_ELEC_ENTITY):
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
        if o.get(CONF_COP_ELEC_ENTITY) and ref_start is not None:
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

        if o.get(CONF_COP_HEAT_ENTITY):
            heat = state_float(self.hass, o.get(CONF_COP_HEAT_ENTITY))
        else:
            raw = data.get(REG_HEAT_YEAR)
            heat = raw * scale if raw is not None else None

        if o.get(CONF_COP_ELEC_ENTITY):
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

    async def write_value(self, address: int, value: int) -> None:
        """Beliebiges Register schreiben – für die interne PV-Steuerung.

        Bewusst ohne anschließenden Refresh-Request (wird ohnehin im selben
        Lesezyklus aufgerufen), um keine Rekursion auszulösen.
        """
        if not self._client.connected:
            await self._client.connect()
        await self._write_holding(address, int(value))

    async def write_setpoint(self, value: int) -> None:
        """Solltemperatur (Reg 6) setzen – für die interne PV-Steuerung."""
        await self.write_value(REG_SET_TEMP, int(value))

    async def async_close(self) -> None:
        try:
            await self.energy.async_save()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass
