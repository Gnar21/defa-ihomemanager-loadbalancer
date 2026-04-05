from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional, Any, Callable, Awaitable

from pymodbus.client import AsyncModbusTcpClient


@dataclass
class ModbusEndpoint:
    host: str
    port: int
    unit: int


class AsyncModbusEndpointClient:
    """Single-connection Modbus TCP client with a lock per endpoint.

    PyModbus API differs across versions (keyword names & keyword-only params). [1](https://www.reddit.com/r/homeassistant/comments/195ypth/help_needed_sending_temperature_to_servicewrite/)
    We always pass count as a keyword and try multiple unit/slave keyword names.
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

    async def _try_unit_kwargs(
        self,
        func: Callable[..., Awaitable[Any]],
        *,
        address: int,
        count: int,
        values: list[int] | None = None,
    ):
        """Try calling pymodbus function with different unit/slave keyword names."""
        # Try the common keyword names used across versions/docs.
        unit_keys = ["slave", "unit", "device_id", "slave_id"]

        # Build candidate kwargs sets
        base_kwargs = {"count": count}  # keep count keyword-only compatible
        if values is None:
            # read_*: typically func(address, **kwargs)
            for key in unit_keys:
                try:
                    return await func(address, **{**base_kwargs, key: self._ep.unit})
                except TypeError:
                    continue
            # last resort: maybe it doesn't take unit at all (single device)
            return await func(address, **base_kwargs)
        else:
            # write_*: func(address, values, **kwargs) OR func(address, values=..., **kwargs)
            # Try positional values first (most common)
            for key in unit_keys:
                try:
                    return await func(address, values, **{key: self._ep.unit})
                except TypeError:
                    pass
                try:
                    return await func(address, values=values, **{key: self._ep.unit})
                except TypeError:
                    continue
            # last resort: no unit keyword
            try:
                return await func(address, values)
            except TypeError:
                return await func(address, values=values)

    async def read_input_registers(self, address: int, count: int):
        async with self._lock:
            await self.async_connect()
            assert self._client is not None
            return await self._try_unit_kwargs(
                self._client.read_input_registers,
                address=address,
                count=count,
            )

    async def write_registers(self, address: int, values: list[int]):
        async with self._lock:
            await self.async_connect()
            assert self._client is not None
            return await self._try_unit_kwargs(
                self._client.write_registers,
                address=address,
                count=0,  # unused for write; kept for signature consistency
                values=values,
            )


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
