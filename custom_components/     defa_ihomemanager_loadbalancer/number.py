from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


# key, friendly_name, min, max, step, unit
NUMBERS = [
    ("fuse_a", "Huvudsäkring per fas (A)", 6, 63, 1, "A"),
    ("margin_a", "Säkerhetsmarginal (A)", 0, 10, 0.5, "A"),
    ("normal_max_a", "Normal: Max laddström (A)", 6, 32, 1, "A"),
    ("min_a", "Min laddström (A)", 0, 10, 1, "A"),

    # ✅ ECO per fas: ställbar
    ("eco_grid_limit_a", "ECO: Max nätström per fas (A)", 0, 10, 0.5, "A"),

    # Teckenkonvention för grid power (+1 / -1)
    ("grid_power_sign", "iHomeManager grid power sign (1/-1)", -1, 1, 2, ""),

    # Anti-fladder
    ("deadband_a", "Anti-fladder: Dödzon (A)", 0, 5, 1, "A"),
    ("ramp_a_per_min", "Anti-fladder: Ramp (A/min)", 1, 6, 1, "A/min"),
    ("min_up_interval_s", "Anti-fladder: Min intervall upp (s)", 0, 300, 10, "s"),
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [LBNumber(hass, entry, coordinator, entry.entry_id, *cfg) for cfg in NUMBERS]
    )


class LBNumber(CoordinatorEntity, NumberEntity):
    def __init__(self, hass, entry, coordinator, entry_id, key, name, min_v, max_v, step, unit):
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_native_min_value = min_v
        self._attr_native_max_value = max_v
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        return getattr(self.coordinator.settings, self._key)

    async def async_set_native_value(self, value: float):
        # 1) Update runtime settings
        setattr(self.coordinator.settings, self._key, float(value))

        # 2) Persist in config entry options (survives restart) via config entries options flow model. [7](https://docs.chipkin.com/articles/modbus-addressing-register-reference/)[8](https://community.home-assistant.io/t/how-to-write-sensor-data-from-ha-to-modbus/537390)
        new_opts = dict(self.entry.options)
        new_opts[self._key] = float(value)
        self.hass.config_entries.async_update_entry(self.entry, options=new_opts)

        await self.coordinator.async_request_refresh()
