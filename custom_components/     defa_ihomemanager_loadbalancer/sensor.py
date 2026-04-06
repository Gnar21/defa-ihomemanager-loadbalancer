from __future__ import annotations

import logging
from homeassistant.components.sensor import SensorEntity
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
    ("total_feed_in_power", "Total feed-in power", "kWh"),  # <-- FIX: underscore, not hyphen
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

    @property
    def native_value(self):
        # coordinator.data can be None until first refresh completes
        data = self.coordinator.data or {}
        val = data.get(self._key)

        # If missing, return None -> HA will show unknown
        if val is None:
            return None

        # Pretty rounding for floats
        return round(val, 3) if isinstance(val, float) else val
