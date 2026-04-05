from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from pymodbus.client import AsyncModbusTcpClient


@dataclass
class ModbusEndpoint:
    host: str
    port: int
    unit: int


class AsyncModbusEndpointClient:
    """Single-connection Modbus TCP client with a lock per endpoint.

    PyModbus API differs across versions (slave= vs unit= vs positional only). [1](https://www.reddit.com/r/homeassistant/comments/195ypth/help_needed_sending_temperature_to_servicewrite/)[2](https://community.home-assistant.io/t/modbus-register/936596)
    We avoid keyword arguments entirely and pass the unit/slave ID positionally.
    """

    def __init__(self, endpoint: ModbusEndpoint) -> None:
        self._ep = endpoint
        self._client: Optional[AsyncModbusTcpClient] = None
        self._lock = asyncio.Lock()

    async def async_connect(self) -> None:
        if self._client is not None and self._client.connected:
            return
        self._client = AsyncModbusTcpClient(host=self._ep.host, port=self._ep.port)
        await self._client.connect()

    async def async_close(self) -> None:
        if self._client is not None:
            await self._client.close()
        self._client = None

    async def read_input_registers(self, address: int, count: int):
        async with self._lock:
            await self.async_connect()
            assert self._client is not None
            # third positional arg is unit/slave depending on PyModbus version [2](https://community.home-assistant.io/t/modbus-register/936596)[4](https://mantikor.github.io/components/sensor.modbus/)
            return await self._client.read_input_registers(address, count, self._ep.unit)

    async def write_registers(self, address: int, values: list[int]):
        async with self._lock:
            await self.async_connect()
            assert self._client is not None
            # third positional arg is unit/slave depending on PyModbus version [3](https://community.home-assistant.io/t/reading-and-writing-modbus-register-solved/373498)[4](https://mantikor.github.io/components/sensor.modbus/)
            return await self._client.write_registers(address, values, self._ep.unit)


def u16(regs: list[int], idx: int = 0) -> int:
    return regs[idx] & 0xFFFF


def u32_big_endian(regs: list[int], idx: int = 0) -> int:
    hi = regs[idx] & 0xFFFF
    lo = regs[idx + 1] & 0xFFFF
    return (hi << 16) | lo


def u32_hybrid_low_word_first(regs: list[int], idx: int = 0) -> int:
    low = regs[idx] & 0xFFFF
    high = regs[idx + 1] & 0xFFFF
    return (high << 16) | low


def s32_hybrid_low_word_first(regs: list[int], idx: int = 0) -> int:
    val = u32_hybrid_low_word_first(regs, idx)
    if val & 0x80000000:
        val -= 0x100000000
    return val
