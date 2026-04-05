from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

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
    ("total_feed-in_power", "Total feed-in power", "kWh"),
    ("total_active_power", "Total active power", "kW"),
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([LBsensor(coordinator, entry.entry_id, k, n, u) for k, n, u in SENSORS])


class LBsensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry_id: str, key: str, name: str, unit: str):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        val = self.coordinator.data.get(self._key)
        if val is None:
            return None
        return round(val, 3) if isinstance(val, float) else val
