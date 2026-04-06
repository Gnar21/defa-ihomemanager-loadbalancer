from __future__ import annotations

import logging
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SENSORS = [
    ("grid_i_l1", "Grid current L1", "A"),
    ("grid_i_l2", "Grid current L2", "A"),
    ("grid_i_l3", "Grid current L3", "A"),
    ("ev_i_l1", "EV current L1", "A"),
    ("ev_i_l2", "EV current L2", "A"),
    ("ev_i_l3", "EV current L3", "A"),
    ("headroom", "Fuse headroom (min phase)", "A"),
    ("export_kw", "Export power", "kW"),
    ("desired", "Desired EV max current", "A"),
    ("applied", "Applied EV max current", "A"),
    ("target_normal", "Target (Normal)", "A"),
    ("target_eco", "Target (Eco)", "A"),

    # Extra sensors
    ("total_purchased_power", "Total Purchased power", "kWh"),
    ("total_feed_in_power", "Total feed-in power", "kWh"),
    ("total_active_power", "Total active power", "kW"),
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [LBSensor(coordinator, entry.entry_id, k, n, u) for k, n, u in SENSORS]
    )


class LBSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry_id: str, key: str, name: str, unit: str):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit

        # ✅ Rätt klassning för energitotaler (kWh)
        # device_class=energy + state_class=total_increasing ger long-term statistics och “meter”-beteende. [1](https://www.defa.com/what-is-full-dynamic-load-balancing/)[2](https://www.defa.com/support/defa-balancer/)[3](https://hacs.xyz/docs/use/download/download/)
        if key in ("total_purchased_power", "total_feed_in_power"):
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        val = data.get(self._key)

        if val is None:
            return None

        # ⚠️ Avrunda inte TOTAL_INCREASING, för att undvika falska “minskningar” p.g.a. rounding. [2](https://www.defa.com/support/defa-balancer/)[5](https://kubernetes-sigs.github.io/aws-load-balancer-controller/v2.1/deploy/installation/)
        if self._key in ("total_purchased_power", "total_feed_in_power"):
            return float(val)

        return round(val, 3) if isinstance(val, float) else val
