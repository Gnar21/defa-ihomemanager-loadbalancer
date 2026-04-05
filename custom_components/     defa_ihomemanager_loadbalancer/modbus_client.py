from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from pymodbus.client import AsyncModbusTcpClient


@dataclass
class ModbusEndpoint:
    host: str
    port: int
    unit: int  # mapped to device_id in this HA Core pymodbus build


class AsyncModbusEndpointClient:
    """Single-connection Modbus TCP client with serialized calls.

    - Keeps one TCP client per endpoint
    - Serializes calls with a lock (PyModbus client is not thread-safe) [2](https://developers.home-assistant.io/docs/architecture/devices-and-services/)
    - Uses HA Core PyModbus signatures:
        read_input_registers(address, *, count=..., device_id=...)
        write_registers(address, values, *, device_id=...)
    """

    def __init__(self, endpoint: ModbusEndpoint) -> None:
        self._ep = endpoint
        self._client: Optional[AsyncModbusTcpClient] = None
        self._lock = asyncio.Lock()

    async def async_connect(self) -> None:
        if self._client is not None and getattr(self._client, "connected", False):
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
            return await self._client.read_input_registers(
                address,
                count=count,               # keyword-only
                device_id=self._ep.unit,   # unit/slave id in your build
            )

    async def read_holding_registers(self, address: int, count: int):
        async with self._lock:
            await self.async_connect()
            assert self._client is not None
            return await self._client.read_holding_registers(
                address,
                count=count,
                device_id=self._ep.unit,
            )

    async def write_registers(self, address: int, values: list[int]):
        async with self._lock:
            await self.async_connect()
            assert self._client is not None
            return await self._client.write_registers(
                address,
                values,                    # positional values (per signature)
                device_id=self._ep.unit,   # keyword-only
            )


# -----------------------
# Register decoding helpers
# -----------------------

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
