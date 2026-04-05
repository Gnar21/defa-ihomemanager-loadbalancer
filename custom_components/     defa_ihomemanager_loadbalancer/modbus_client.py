from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional, Any

from pymodbus.client import AsyncModbusTcpClient


@dataclass
class ModbusEndpoint:
    host: str
    port: int
    unit: int


class AsyncModbusEndpointClient:
    """Single-connection Modbus TCP client with a lock per endpoint.

    PyModbus API differs across versions:
      - Some accept slave= keyword
      - Some accept unit= keyword
      - Some accept NO keyword and require unit/slave as positional arg

    We try all three patterns. PyModbus docs show slave= in current examples. [2](https://community.home-assistant.io/t/modbus-register/936596)[3](https://newerest.space/mastering-modbus-integration-home-assistant/)
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

    async def _call_with_unit(self, func, *args, **kwargs) -> Any:
        """Call a pymodbus client function with best-effort unit/slave handling."""
        # 1) Try modern kwarg: slave=
        try:
            return await func(*args, **{**kwargs, "slave": self._ep.unit})
        except TypeError:
            pass

        # 2) Try alternative kwarg: unit=
        try:
            return await func(*args, **{**kwargs, "unit": self._ep.unit})
        except TypeError:
            pass

        # 3) Fallback: positional unit/slave as last positional argument
        return await func(*args, self._ep.unit, **kwargs)

    async def read_input_registers(self, address: int, count: int):
        async with self._lock:
            await self.async_connect()
            assert self._client is not None
            # read_input_registers is the FC04 call in PyModbus docs. [3](https://newerest.space/mastering-modbus-integration-home-assistant/)
            return await self._call_with_unit(
                self._client.read_input_registers, address, count
            )

    async def write_registers(self, address: int, values: list[int]):
        async with self._lock:
            await self.async_connect()
            assert self._client is not None
            # write_registers is the FC16 call in PyModbus docs. [4](https://community.home-assistant.io/t/reading-and-writing-modbus-register-solved/373498)[3](https://newerest.space/mastering-modbus-integration-home-assistant/)
            return await self._call_with_unit(
                self._client.write_registers, address, values
            )


def u16(regs: list[int], idx: int = 0) -> int:
    return regs[idx] & 0xFFFF


def u32_big_endian(regs: list[int], idx: int = 0) -> int:
    """Two registers, high word first (big-endian over registers)."""
    hi = regs[idx] & 0xFFFF
    lo = regs[idx + 1] & 0xFFFF
    return (hi << 16) | lo


def u32_hybrid_low_word_first(regs: list[int], idx: int = 0) -> int:
    """iHomeManager U32: low-word first."""
    low = regs[idx] & 0xFFFF
    high = regs[idx + 1] & 0xFFFF
    return (high << 16) | low


def s32_hybrid_low_word_first(regs: list[int], idx: int = 0) -> int:
    """iHomeManager S32: low-word first, signed."""
    val = u32_hybrid_low_word_first(regs, idx)
    if val & 0x80000000:
        val -= 0x100000000
    return val
