"""Modbus-Client je Verbindungsart (TCP-Konverter oder serieller RTU-Adapter, #16).

Bewusst ohne HA-Abhängigkeiten, damit Coordinator und Config-Flow (Verbindungstest)
denselben Aufbau nutzen.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

from pymodbus.client import AsyncModbusSerialClient, AsyncModbusTcpClient

from .const import (
    CONF_BAUDRATE,
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_PORT,
    CONF_SERIAL_PORT,
    CONNECTION_SERIAL,
    DEFAULT_BAUDRATE,
    DEFAULT_CONNECTION_TYPE,
    DEFAULT_PORT,
    SERIAL_BYTESIZE,
    SERIAL_PARITY,
    SERIAL_STOPBITS,
)


def connection_settings(options: Mapping[str, Any], data: Mapping[str, Any]) -> dict[str, Any]:
    """Verbindungsdaten: Options haben Vorrang (im GUI änderbar), sonst Setup-Daten."""

    def cur(key: str, default: Any = None) -> Any:
        return options.get(key, data.get(key, default))

    return {
        CONF_CONNECTION_TYPE: cur(CONF_CONNECTION_TYPE, DEFAULT_CONNECTION_TYPE),
        CONF_HOST: cur(CONF_HOST, ""),
        CONF_PORT: cur(CONF_PORT, DEFAULT_PORT),
        CONF_SERIAL_PORT: cur(CONF_SERIAL_PORT, ""),
        CONF_BAUDRATE: cur(CONF_BAUDRATE, DEFAULT_BAUDRATE),
    }


def is_serial(settings: Mapping[str, Any]) -> bool:
    return settings.get(CONF_CONNECTION_TYPE) == CONNECTION_SERIAL


def describe(settings: Mapping[str, Any]) -> str:
    """Kurzbeschreibung des Ziels für Log-/Fehlermeldungen."""
    if is_serial(settings):
        return f"seriell {settings[CONF_SERIAL_PORT]} ({settings[CONF_BAUDRATE]} 8N1)"
    return f"{settings[CONF_HOST]}:{settings[CONF_PORT]}"


def create_client(settings: Mapping[str, Any], timeout: float = 3, retries: int = 1):
    """pymodbus-Client passend zur Verbindungsart bauen.

    Seriell: RTU-Framer ist der pymodbus-Standard des Serial-Clients (3.6 bis
    3.16 geprüft); benötigt ``pyserial`` (in manifest.json gelistet).
    """
    if is_serial(settings):
        return AsyncModbusSerialClient(
            settings[CONF_SERIAL_PORT],
            baudrate=int(settings[CONF_BAUDRATE]),
            bytesize=SERIAL_BYTESIZE,
            parity=SERIAL_PARITY,
            stopbits=SERIAL_STOPBITS,
            timeout=timeout,
            retries=retries,
        )
    return AsyncModbusTcpClient(
        settings[CONF_HOST], port=int(settings[CONF_PORT]), timeout=timeout, retries=retries
    )


def unit_kwargs(method, unit: int) -> dict[str, int]:
    """Slave-Adresse unter dem Namen, den diese pymodbus-Version erwartet.

    pymodbus hat ``slave=`` in ``device_id=`` umbenannt. Ältere Versionen (z. B.
    3.6.x) nehmen ein unbekanntes ``device_id=`` stillschweigend in ``**kwargs``
    auf und senden dann mit Adresse 0 (Broadcast) – ein ``TypeError`` als
    Erkennung greift dort nicht. Am seriellen RTU-Bus antwortet ein Gerät auf
    Broadcast-Lesezugriffe nie. Daher den Namen aus der Signatur ableiten.
    """
    try:
        params = inspect.signature(method).parameters
    except (TypeError, ValueError):
        params = {}
    if "device_id" in params:
        return {"device_id": unit}
    if "slave" in params:
        return {"slave": unit}
    return {"device_id": unit}
