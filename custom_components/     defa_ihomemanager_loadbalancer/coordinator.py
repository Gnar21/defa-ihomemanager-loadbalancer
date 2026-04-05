from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
import time

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_FUSE_A,
    DEFAULT_MARGIN_A,
    DEFAULT_NORMAL_MAX_A,
    DEFAULT_MIN_A,
    DEFAULT_ECO_GRID_LIMIT_A,
    DEFAULT_GRID_POWER_SIGN,
    DEFAULT_DEADBAND_A,
    DEFAULT_RAMP_A_PER_MIN,
    DEFAULT_MIN_UP_INTERVAL_S,
)
from .modbus_client import (
    AsyncModbusEndpointClient,
    u16,
    u32_hybrid_low_word_first,
    s32_hybrid_low_word_first,
    u32_big_endian,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class Settings:
    fuse_a: float = DEFAULT_FUSE_A
    margin_a: float = DEFAULT_MARGIN_A
    normal_max_a: float = DEFAULT_NORMAL_MAX_A
    min_a: float = DEFAULT_MIN_A

    eco_grid_limit_a: float = DEFAULT_ECO_GRID_LIMIT_A
    grid_power_sign: int = DEFAULT_GRID_POWER_SIGN
    eco_mode: bool = False

    deadband_a: float = DEFAULT_DEADBAND_A
    ramp_a_per_min: float = DEFAULT_RAMP_A_PER_MIN
    min_up_interval_s: int = DEFAULT_MIN_UP_INTERVAL_S


class LoadBalancerCoordinator(DataUpdateCoordinator[dict]):
    def __init__(
        self,
        hass: HomeAssistant,
        ihm: AsyncModbusEndpointClient,
        defa: AsyncModbusEndpointClient,
        settings: Settings,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,  # ✅ REQUIRED
            name="DEFA+iHomeManager Load Balancer",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self._ihm = ihm
        self._defa = defa
        self.settings = settings

        self._last_sent_a: float = 0.0
        self._last_up_ts: float = 0.0

    async def close(self) -> None:
        await self._ihm.async_close()
        await self._defa.async_close()

    async def _async_update_data(self) -> dict:
        try:
            # --------------------------
            # iHomeManager: voltages
            # 8555-8557 (we use reg-1 addresses here as per earlier setup)
            # --------------------------
            v_regs = await self._ihm.read_input_registers(8554, 3)
            if v_regs.isError():
                raise UpdateFailed(f"iHomeManager voltage read error: {v_regs}")
            v_l1 = u16(v_regs.registers, 0) * 0.1
            v_l2 = u16(v_regs.registers, 1) * 0.1
            v_l3 = u16(v_regs.registers, 2) * 0.1
            v_avg = max((v_l1 + v_l2 + v_l3) / 3.0, 1.0)

            # --------------------------
            # iHomeManager: phase active power (8559-8564 U32 W)
            # --------------------------
            p1 = await self._ihm.read_input_registers(8558, 2)
            p2 = await self._ihm.read_input_registers(8560, 2)
            p3 = await self._ihm.read_input_registers(8562, 2)
            if p1.isError() or p2.isError() or p3.isError():
                raise UpdateFailed("iHomeManager phase power read error")
            p_l1 = float(u32_hybrid_low_word_first(p1.registers, 0))
            p_l2 = float(u32_hybrid_low_word_first(p2.registers, 0))
            p_l3 = float(u32_hybrid_low_word_first(p3.registers, 0))

            # --------------------------
            # iHomeManager: grid meter active power (8157 S32, 0.01 kW) -> address 8156
            # --------------------------
            gp = await self._ihm.read_input_registers(8156, 2)
            if gp.isError():
                raise UpdateFailed("iHomeManager grid power read error")
            grid_kw = s32_hybrid_low_word_first(gp.registers, 0) * 0.01
            grid_kw *= int(self.settings.grid_power_sign)

            # --------------------------
            # EXTRA sensors (som du ville ha)
            # address, data_type, scale som du la in
            # --------------------------
            tp = await self._ihm.read_input_registers(8175, 2)  # Total Purchased power (U32) scale 0.1 kWh
            tf = await self._ihm.read_input_registers(8177, 2)  # Total feed-in power (U32) scale 0.1 kWh
            ta = await self._ihm.read_input_registers(8156, 2)  # Total active power (S32) scale 0.01 kW (din adress)
            if tp.isError() or tf.isError() or ta.isError():
                raise UpdateFailed("iHomeManager extra sensors read error")

            total_purchased_power = u32_hybrid_low_word_first(tp.registers, 0) * 0.1
            total_feed_in_power = u32_hybrid_low_word_first(tf.registers, 0) * 0.1
            total_active_power = s32_hybrid_low_word_first(ta.registers, 0) * 0.01

            # --------------------------
            # DEFA: EV currents per phase (mA -> A)
            # --------------------------
            i1 = await self._defa.read_input_registers(293, 2)
            i2 = await self._defa.read_input_registers(296, 2)
            i3 = await self._defa.read_input_registers(299, 2)
            if i1.isError() or i2.isError() or i3.isError():
                raise UpdateFailed("DEFA current read error")

            ev_i_l1 = u32_big_endian(i1.registers, 0) * 0.001
            ev_i_l2 = u32_big_endian(i2.registers, 0) * 0.001
            ev_i_l3 = u32_big_endian(i3.registers, 0) * 0.001

            # --------------------------
            # Calculate grid currents per phase ~ P/V
            # --------------------------
            grid_i_l1 = p_l1 / max(v_l1, 1.0)
            grid_i_l2 = p_l2 / max(v_l2, 1.0)
            grid_i_l3 = p_l3 / max(v_l3, 1.0)

            other_l1 = max(grid_i_l1 - ev_i_l1, 0.0)
            other_l2 = max(grid_i_l2 - ev_i_l2, 0.0)
            other_l3 = max(grid_i_l3 - ev_i_l3, 0.0)

            fuse = self.settings.fuse_a
            margin = self.settings.margin_a
            headroom = min(
                fuse - margin - other_l1,
                fuse - margin - other_l2,
                fuse - margin - other_l3,
            )

            # NORMAL target
            normal_target = min(max(headroom, 0.0), self.settings.normal_max_a)
            if normal_target < self.settings.min_a:
                normal_target = 0.0

            # ECO target (per fas)
            export_kw = max(-grid_kw, 0.0)
            solar_a_per_phase = (export_kw * 1000.0) / (3.0 * v_avg)
            eco_limit = solar_a_per_phase + self.settings.eco_grid_limit_a
            eco_target = min(max(0.0, min(headroom, eco_limit, self.settings.normal_max_a)), self.settings.normal_max_a)
            if eco_target < self.settings.min_a:
                eco_target = 0.0

            desired = eco_target if self.settings.eco_mode else normal_target
            applied = self._apply_antifladder(desired)

            # --------------------------
            # Write to DEFA: alive + eMS max current
            # alive 2008-2009 write uint32=1; eMS max current 2000-2001 mA
            # --------------------------
            await self._defa.write_registers(2008, [0, 1])  # alive [9](https://github.com/hacs)

            ma = int(round(applied * 1000.0))
            hi = (ma >> 16) & 0xFFFF
            lo = ma & 0xFFFF
            await self._defa.write_registers(2000, [hi, lo])  # eMS max current [9](https://github.com/hacs)

            return {
                "grid_i_l1": grid_i_l1,
                "grid_i_l2": grid_i_l2,
                "grid_i_l3": grid_i_l3,
                "ev_i_l1": ev_i_l1,
                "ev_i_l2": ev_i_l2,
                "ev_i_l3": ev_i_l3,
                "headroom": headroom,
                "export_kw": export_kw,
                "desired": desired,
                "applied": applied,
                "target_normal": normal_target,
                "target_eco": eco_target,

                # Extra sensors:
                "total_purchased_power": total_purchased_power,
                "total_feed-in_power": total_feed_in_power,
                "total_active_power": total_active_power,
            }

        except Exception as err:
            raise UpdateFailed(err) from err

    def _apply_antifladder(self, desired: float) -> float:
        deadband = float(self.settings.deadband_a)
        ramp_per_min = float(self.settings.ramp_a_per_min)
        min_up_s = int(self.settings.min_up_interval_s)

        now = time.time()
        current = self._last_sent_a
        diff = desired - current

        if abs(diff) < deadband:
            return current

        # Down: immediate (säkringsskydd)
        if diff < 0:
            self._last_sent_a = max(desired, 0.0)
            return self._last_sent_a

        # Up: rate limit
        if (now - self._last_up_ts) < min_up_s:
            return current

        # Up: ramp (10s interval => 6 steg per minut)
        step = max(ramp_per_min / 6.0, 0.1)
        new_val = min(current + step, desired)

        self._last_sent_a = new_val
        self._last_up_ts = now
        return new_val
