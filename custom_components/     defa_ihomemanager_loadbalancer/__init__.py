from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import LoadBalancerCoordinator, Settings
from .modbus_client import AsyncModbusEndpointClient, ModbusEndpoint

PLATFORMS = ["sensor", "number", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ihm = AsyncModbusEndpointClient(
        ModbusEndpoint(
            host=entry.data["ihomemanager_host"],
            port=entry.data["ihomemanager_port"],
            unit=entry.data["ihomemanager_unit"],
        )
    )
    defa = AsyncModbusEndpointClient(
        ModbusEndpoint(
            host=entry.data["defa_host"],
            port=entry.data["defa_port"],
            unit=entry.data["defa_unit"],
        )
    )

    opts = entry.options
    settings = Settings(
        fuse_a=opts.get("fuse_a", 20.0),
        margin_a=opts.get("margin_a", 2.0),
        normal_max_a=opts.get("normal_max_a", 16.0),
        min_a=opts.get("min_a", 6.0),
        eco_grid_limit_a=opts.get("eco_grid_limit_a", 2.0),
        grid_power_sign=int(opts.get("grid_power_sign", 1)),
        eco_mode=bool(opts.get("eco_mode", False)),
        deadband_a=opts.get("deadband_a", 1.0),
        ramp_a_per_min=opts.get("ramp_a_per_min", 2.0),
        min_up_interval_s=int(opts.get("min_up_interval_s", 60)),
    )

    coordinator = LoadBalancerCoordinator(hass, ihm, defa, settings)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "entry": entry,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id, {})
        coordinator = data.get("coordinator")
        if coordinator:
            await coordinator.close()
    return unload_ok
