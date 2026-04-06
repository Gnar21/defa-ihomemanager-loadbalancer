from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Optional, Any, Callable

from pymodbus.client import AsyncModbusTcpClient

_LOGGER = logging.getLogger(__name__)


@dataclass
class ModbusEndpoint:
    host: str
    port: int
    unit: int  # unit id / slave id / device_id depending on pymodbus build


class AsyncModbusEndpointClient:
    """Single-connection Modbus TCP client with serialized calls.

    - Keeps one TCP client per endpoint.
    - Serializes calls with a lock (avoid concurrent requests on same socket).
    - Handles pymodbus kwarg differences for unit id (device_id vs slave vs unit).
      (This is needed because pymodbus changed identifiers across versions.) [1](https://community.home-assistant.io/t/managing-pymodbus-versions-in-custom-integrations/823773)
    """

    def __init__(self, endpoint: ModbusEndpoint) -> None:
        self._ep = endpoint
        self._client: Optional[AsyncModbusTcpClient] = None
        self._lock = asyncio.Lock()

    async def async_connect(self) -> None:
        """Ensure we have a connected client."""
        if self._client is not None and getattr(self._client, "connected", False):
            return

        self._client = AsyncModbusTcpClient(host=self._ep.host, port=self._ep.port)
        await self._client.connect()

    async def async_close(self) -> None:
        """Close and drop the client."""
        if self._client is not None:
            try:
                await self._client.close()
            finally:
                self._client = None

    async def _call_with_unit_kw(
        self,
        fn: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ):
        """Call a pymodbus function using the correct unit keyword.

        We try device_id first (newer pymodbus / HA builds), then slave, then unit.
        Only one will match the installed pymodbus signature. [1](https://community.home-assistant.io/t/managing-pymodbus-versions-in-custom-integrations/823773)
        """
        unit_value = self._ep.unit

        # IMPORTANT: do NOT pass any of these unless we're trying them,
        # because passing the wrong one causes the exact error you're seeing.
        tries = ("device_id", "slave", "unit")

        last_err: Exception | None = None
        for key in tries:
            try:
                call_kwargs = dict(kwargs)
                call_kwargs[key] = unit_value
                return await fn(*args, **call_kwargs)
            except TypeError as e:
                # wrong kwarg for this pymodbus build => try next
                last_err = e
                continue

        # If we get here, none of the known keywords worked
        raise last_err if last_err is not None else TypeError("Unknown Modbus unit kwarg mismatch")

    async def read_input_registers(self, address: int, count: int):
        async with self._lock:
            await self.async_connect()
            assert self._client is not None

            return await self._call_with_unit_kw(
                self._client.read_input_registers,
                address=address,
                count=count,
            )

    async def read_holding_registers(self, address: int, count: int):
        async with self._lock:
            await self.async_connect()
            assert self._client is not None

            return await self._call_with_unit_kw(
                self._client.read_holding_registers,
                address=address,
                count=count,
            )

    async def write_registers(self, address: int, values: list[int]):
        async with self._lock:
            await self.async_connect()
            assert self._client is not None

            # Some pymodbus builds accept values as positional, others as keyword;
            # using keyword is usually safest.
            return await self._call_with_unit_kw(
                self._client.write_registers,
                address=address,
                values=values,
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
