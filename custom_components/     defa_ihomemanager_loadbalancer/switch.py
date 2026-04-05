from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([EcoModeSwitch(hass, entry, coordinator, entry.entry_id)])


class EcoModeSwitch(CoordinatorEntity, SwitchEntity):
    _attr_name = "EV Eco-läge (Sol/Batteri)"
    _attr_icon = "mdi:leaf"

    def __init__(self, hass, entry, coordinator, entry_id: str):
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{entry_id}_eco_mode"

    @property
    def is_on(self):
        return bool(self.coordinator.settings.eco_mode)

    async def async_turn_on(self, **kwargs):
        self.coordinator.settings.eco_mode = True
        new_opts = dict(self.entry.options)
        new_opts["eco_mode"] = True
        # Persist using config entry options storage. [7](https://docs.chipkin.com/articles/modbus-addressing-register-reference/)[8](https://community.home-assistant.io/t/how-to-write-sensor-data-from-ha-to-modbus/537390)
        self.hass.config_entries.async_update_entry(self.entry, options=new_opts)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        self.coordinator.settings.eco_mode = False
        new_opts = dict(self.entry.options)
        new_opts["eco_mode"] = False
        # Persist using config entry options storage. [7](https://docs.chipkin.com/articles/modbus-addressing-register-reference/)[8](https://community.home-assistant.io/t/how-to-write-sensor-data-from-ha-to-modbus/537390)
        self.hass.config_entries.async_update_entry(self.entry, options=new_opts)
        await self.coordinator.async_request_refresh()
``
