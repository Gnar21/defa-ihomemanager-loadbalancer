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


def _ensure_ok(resp, label: str) -> None:
    """Raise UpdateFailed with a useful message if a modbus response is error."""
    if resp is None:
        raise UpdateFailed(f"{label}: response is None")
    if hasattr(resp, "isError") and resp.isError():
        raise UpdateFailed(f"{label}: {resp}")
    if not hasattr(resp, "registers"):
        raise UpdateFailed(f"{label}: missing registers attribute ({resp})")


def _zero_deadband(x: float, band: float) -> float:
    """Return 0.0 when value is close to 0 (to reduce flapping at import/export boundary)."""
    return 0.0 if abs(x) < band else x


def _clamp(x: float, low: float, high: float) -> float:
    """Clamp float to a range."""
    if x != x:  # NaN
        return 0.0
    return max(low, min(high, x))


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
    """Poll iHomeManager + DEFA and apply limit to DEFA.

    Uses Home Assistant DataUpdateCoordinator pattern. [3](https://developers.home-assistant.io/docs/integration_fetching_data/)[2](https://developers.home-assistant.io/blog/2024/08/05/coordinator_async_setup/)
    """

    def __init__(
        self,
        hass: HomeAssistant,
        ihm: AsyncModbusEndpointClient,
        defa: AsyncModbusEndpointClient,
        settings: Settings,
    ) -> None:
        # DataUpdateCoordinator requires logger in newer HA versions. [1](https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/update_coordinator.py)[2](https://developers.home-assistant.io/blog/2024/08/05/coordinator_async_setup/)
        super().__init__(
            hass=hass,
            logger=_LOGGER,
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
        """Fetch data and (best-effort) apply control.

        If DEFA reads/writes fail, we still return iHomeManager data so entities
        do not get stuck as unknown.
        """
        try:
            # --------------------------
            # iHomeManager reads (required)
            # --------------------------
            # Voltages: 8555-8557 -> address 8554, U16, scale 0.1V
            v_regs = await self._ihm.read_input_registers(8554, 3)
            _ensure_ok(v_regs, "iHomeManager voltages @8554 count=3")
            v_l1 = u16(v_regs.registers, 0) * 0.1
            v_l2 = u16(v_regs.registers, 1) * 0.1
            v_l3 = u16(v_regs.registers, 2) * 0.1
            v_avg = max((v_l1 + v_l2 + v_l3) / 3.0, 1.0)

            # Phase active power:
            # Phase A: 8559~8560 -> address 8558 (2 regs)
            # Phase B: 8561~8562 -> address 8560 (2 regs)
            # Phase C: 8563~8564 -> address 8562 (2 regs)
            p1 = await self._ihm.read_input_registers(8558, 2)
            _ensure_ok(p1, "iHomeManager phase power A @8558 count=2")
            p2 = await self._ihm.read_input_registers(8560, 2)
            _ensure_ok(p2, "iHomeManager phase power B @8560 count=2")
            p3 = await self._ihm.read_input_registers(8562, 2)
            _ensure_ok(p3, "iHomeManager phase power C @8562 count=2")

            # IMPORTANT:
            # Protocol states negative numbers are complements (two's complement).
            # That means phase power can be negative at export -> decode as signed 32-bit.
            p_a = float(s32_hybrid_low_word_first(p1.registers, 0))
            p_b = float(s32_hybrid_low_word_first(p2.registers, 0))
            p_c = float(s32_hybrid_low_word_first(p3.registers, 0))

            # Small deadband around 0W to reduce flapping at import/export boundary.
            p_a = _zero_deadband(p_a, 50.0)
            p_b = _zero_deadband(p_b, 50.0)
            p_c = _zero_deadband(p_c, 50.0)

            # Grid meter active power (total) S32, 0.01 kW: 8157 -> address 8156 (2 regs)
            gp = await self._ihm.read_input_registers(8156, 2)
            _ensure_ok(gp, "iHomeManager grid power @8156 count=2")
            grid_kw = s32_hybrid_low_word_first(gp.registers, 0) * 0.01
            grid_kw *= int(self.settings.grid_power_sign)

            # --------------------------
            # Extra iHomeManager sensors (optional)
            # --------------------------
            total_purchased_power = None
            total_feed_in_power = None
            total_active_power = None

            try:
                tp = await self._ihm.read_input_registers(8175, 2)
                _ensure_ok(tp, "iHomeManager Total Purchased power @8175 count=2")
                tf = await self._ihm.read_input_registers(8177, 2)
                _ensure_ok(tf, "iHomeManager Total feed-in power @8177 count=2")
                ta = await self._ihm.read_input_registers(8156, 2)
                _ensure_ok(ta, "iHomeManager Total active power @8156 count=2")

                # Keep your previous scaling (as you used before).
                total_purchased_power = u32_hybrid_low_word_first(tp.registers, 0) * 0.1
                total_feed_in_power = u32_hybrid_low_word_first(tf.registers, 0) * 0.1
                total_active_power = s32_hybrid_low_word_first(ta.registers, 0) * 0.01
            except Exception as e:
                _LOGGER.debug("Optional iHomeManager extra sensors failed: %s", e)

            # --------------------------
            # DEFA reads (best-effort)
            # --------------------------
            ev_i_l1 = 0.0
            ev_i_l2 = 0.0
            ev_i_l3 = 0.0
            defa_ok = True

            try:
                i1 = await self._defa.read_input_registers(293, 2)
                _ensure_ok(i1, "DEFA current L1 @293 count=2")
                i2 = await self._defa.read_input_registers(296, 2)
                _ensure_ok(i2, "DEFA current L2 @296 count=2")
                i3 = await self._defa.read_input_registers(299, 2)
                _ensure_ok(i3, "DEFA current L3 @299 count=2")

                # DEFA currents are read as big-endian uint32 * 0.001 A (as you had).
                ev_i_l1 = u32_big_endian(i1.registers, 0) * 0.001
                ev_i_l2 = u32_big_endian(i2.registers, 0) * 0.001
                ev_i_l3 = u32_big_endian(i3.registers, 0) * 0.001
            except Exception as e:
                defa_ok = False
                _LOGGER.warning("DEFA read failed (will still publish iHomeManager data): %s", e)

            # --------------------------
            # Compute derived currents
            # --------------------------
            # Convert phase active power (W) to approximate current (A): I ~= P / V
            # Clamp to avoid any unrealistic spikes affecting control.
            grid_i_l1 = _clamp(p_a / max(v_l1, 1.0), -200.0, 200.0)
            grid_i_l2 = _clamp(p_b / max(v_l2, 1.0), -200.0, 200.0)
            grid_i_l3 = _clamp(p_c / max(v_l3, 1.0), -200.0, 200.0)

            # Other load per phase (exclude EV current). If grid current is negative (export),
            # treat "other load" as 0 for headroom purposes.
            other_l1 = max(grid_i_l1 - ev_i_l1, 0.0)
            other_l2 = max(grid_i_l2 - ev_i_l2, 0.0)
            other_l3 = max(grid_i_l3 - ev_i_l3, 0.0)

            fuse = float(self.settings.fuse_a)
            margin = float(self.settings.margin_a)

            headroom = min(
                fuse - margin - other_l1,
                fuse - margin - other_l2,
                fuse - margin - other_l3,
            )

            # NORMAL target
            normal_target = min(max(headroom, 0.0), float(self.settings.normal_max_a))
            if normal_target < float(self.settings.min_a):
                normal_target = 0.0

            # ECO target (per phase)
            export_kw = max(-grid_kw, 0.0)
            solar_a_per_phase = (export_kw * 1000.0) / (3.0 * v_avg)
            eco_limit = solar_a_per_phase + float(self.settings.eco_grid_limit_a)

            eco_target = min(
                max(0.0, min(headroom, eco_limit, float(self.settings.normal_max_a))),
                float(self.settings.normal_max_a),
            )
            if eco_target < float(self.settings.min_a):
                eco_target = 0.0

            desired = eco_target if bool(self.settings.eco_mode) else normal_target
            applied = self._apply_antifladder(desired)

            # --------------------------
            # DEFA writes (best-effort)
            # --------------------------
            if defa_ok:
                try:
                    # alive (uint32=1) to 2008-2009, then eMS max current (mA) to 2000-2001
                    await self._defa.write_registers(2008, [0, 1])

                    ma = int(round(applied * 1000.0))
                    hi = (ma >> 16) & 0xFFFF
                    lo = ma & 0xFFFF
                    await self._defa.write_registers(2000, [hi, lo])
                except Exception as e:
                    _LOGGER.warning("DEFA write failed (continuing with sensor updates): %s", e)

            # --------------------------
            # Return coordinator data
            # --------------------------
            data: dict = {
                "v_l1": v_l1,
                "v_l2": v_l2,
                "v_l3": v_l3,

                # Phase power (signed W)
                "p_l1": p_a,
                "p_l2": p_b,
                "p_l3": p_c,

                "grid_kw": grid_kw,
                "export_kw": export_kw,

                "grid_i_l1": grid_i_l1,
                "grid_i_l2": grid_i_l2,
                "grid_i_l3": grid_i_l3,

                "ev_i_l1": ev_i_l1,
                "ev_i_l2": ev_i_l2,
                "ev_i_l3": ev_i_l3,

                "headroom": headroom,
                "target_normal": normal_target,
                "target_eco": eco_target,
                "desired": desired,
                "applied": applied,
            }

            # Optional extra sensors (underscore keys)
            if total_purchased_power is not None:
                data["total_purchased_power"] = total_purchased_power
            if total_feed_in_power is not None:
                data["total_feed_in_power"] = total_feed_in_power
            if total_active_power is not None:
                data["total_active_power"] = total_active_power

            return data

        except Exception as err:
            _LOGGER.exception("Coordinator refresh failed")
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

        # Down: immediate
        if diff < 0:
            self._last_sent_a = max(desired, 0.0)
            return self._last_sent_a

        # Up: rate limit
        if (now - self._last_up_ts) < min_up_s:
            return current

        # Up: ramp assuming DEFAULT_SCAN_INTERVAL=10s => ~6 steps/min
        step = max(ramp_per_min / 6.0, 0.1)
        new_val = min(current + step, desired)

        self._last_sent_a = new_val
        self._last_up_ts = now
        return new_val
