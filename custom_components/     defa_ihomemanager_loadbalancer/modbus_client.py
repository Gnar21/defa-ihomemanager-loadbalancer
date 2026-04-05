from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from pymodbus.client import AsyncModbusTcpClient


@dataclass
class ModbusEndpoint:
    host: str
    port: int
    unit: int  # will be passed as device_id in PyModbus 3.11.x (HA Core runtime)


class AsyncModbusEndpointClient:
    """Async Modbus TCP endpoint wrapper.

    - Keeps a single TCP client per endpoint.
    - Serializes requests with a lock (PyModbus client is not thread-safe). [1](https://developers.home-assistant.io/docs/architecture/devices-and-services/)
    - Uses PyModbus 3.11.x style kwargs: device_id=... and keyword-only count. [2](https://deepwiki.com/home-assistant/home-assistant.io/7-entity-platform-system)
    """

    def __init__(self, endpoint: ModbusEndpoint) -> None:
        self._ep = endpoint
        self._client: Optional[AsyncModbusTcpClient] = None
        self._lock = asyncio.Lock()

    async def async_connect(self) -> None:
        """Connect (or reuse existing connection)."""
        if self._client is not None and getattr(self._client, "connected", False):
            return
        self._client = AsyncModbusTcpClient(host=self._ep.host, port=self._ep.port)
        await self._client.connect()

    async def async_close(self) -> None:
        """Close the connection."""
        if self._client is not None:
            await self._client.close()
        self._client = None

    async def read_input_registers(self, address: int, count: int):
        """Read input registers (FC04)."""
        async with self._lock:
            await self.async_connect()
            assert self._client is not None
            return await self._client.read_input_registers(
                address,
                count=count,              # keyword-only in your HA runtime
                device_id=self._ep.unit,  # unit/slave id in your HA runtime
            )

    async def read_holding_registers(self, address: int, count: int):
        """Read holding registers (FC03). Included for completeness."""
        async with self._lock:
            await self.async_connect()
            assert self._client is not None
            return await self._client.read_holding_registers(
                address,
                count=count,
                device_id=self._ep.unit,
            )

    async def write_registers(self, address: int, values: list[int]):
        """Write multiple holding registers (FC16)."""
        async with self._lock:
            await self.async_connect()
            assert self._client is not None
            return await self._client.write_registers(
                address,
                values=values,
                device_id=self._ep.unit,
            )


# -----------------------
# Register decoding helpers
# -----------------------

def u16(regs: list[int], idx: int = 0) -> int:
    return regs[idx] & 0xFFFF


def u32_big_endian(regs: list[int], idx: int = 0) -> int:
    """Two registers, high word first (big-endian across registers)."""
    hi = regs[idx] & 0xFFFF
    lo = regs[idx + 1] & 0xFFFF
    return (hi << 16) | lo


def u32_hybrid_low_word_first(regs: list[int], idx: int = 0) -> int:
    """Two registers, low word first (word swap)."""
    low = regs[idx] & 0xFFFF
    high = regs[idx + 1] & 0xFFFF
    return (high << 16) | low


def s32_hybrid_low_word_first(regs: list[int], idx: int = 0) -> int:
    """Signed 32-bit, low word first."""
    val = u32_hybrid_low_word_first(regs, idx)
    if val & 0x80000000:
        val -= 0x100000000
    return val
