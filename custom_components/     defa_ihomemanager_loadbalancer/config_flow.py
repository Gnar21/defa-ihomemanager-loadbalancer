from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries

from .const import (
    DOMAIN,
    CONF_IHM_HOST, CONF_IHM_PORT, CONF_IHM_UNIT,
    CONF_DEFA_HOST, CONF_DEFA_PORT, CONF_DEFA_UNIT,
    DEFAULT_IHM_HOST, DEFAULT_IHM_PORT, DEFAULT_IHM_UNIT,
    DEFAULT_DEFA_HOST, DEFAULT_DEFA_PORT, DEFAULT_DEFA_UNIT,
    DEFAULT_FUSE_A, DEFAULT_MARGIN_A, DEFAULT_NORMAL_MAX_A, DEFAULT_MIN_A,
    DEFAULT_ECO_GRID_LIMIT_A, DEFAULT_GRID_POWER_SIGN,
    DEFAULT_DEADBAND_A, DEFAULT_RAMP_A_PER_MIN, DEFAULT_MIN_UP_INTERVAL_S,
)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_IHM_HOST, default=DEFAULT_IHM_HOST): str,
        vol.Required(CONF_IHM_PORT, default=DEFAULT_IHM_PORT): int,
        vol.Required(CONF_IHM_UNIT, default=DEFAULT_IHM_UNIT): int,
        vol.Required(CONF_DEFA_HOST, default=DEFAULT_DEFA_HOST): str,
        vol.Required(CONF_DEFA_PORT, default=DEFAULT_DEFA_PORT): int,
        vol.Required(CONF_DEFA_UNIT, default=DEFAULT_DEFA_UNIT): int,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)
        return self.async_create_entry(title="DEFA + iHomeManager Load Balancer", data=user_input)


class OptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional("eco_mode", default=opts.get("eco_mode", False)): bool,
                vol.Optional("fuse_a", default=opts.get("fuse_a", DEFAULT_FUSE_A)): vol.Coerce(float),
                vol.Optional("margin_a", default=opts.get("margin_a", DEFAULT_MARGIN_A)): vol.Coerce(float),
                vol.Optional("normal_max_a", default=opts.get("normal_max_a", DEFAULT_NORMAL_MAX_A)): vol.Coerce(float),
                vol.Optional("min_a", default=opts.get("min_a", DEFAULT_MIN_A)): vol.Coerce(float),

                # Eco per phase (configurable)
                vol.Optional("eco_grid_limit_a", default=opts.get("eco_grid_limit_a", DEFAULT_ECO_GRID_LIMIT_A)): vol.Coerce(float),
                vol.Optional("grid_power_sign", default=opts.get("grid_power_sign", DEFAULT_GRID_POWER_SIGN)): vol.In([1, -1]),

                # Anti-fladder
                vol.Optional("deadband_a", default=opts.get("deadband_a", DEFAULT_DEADBAND_A)): vol.Coerce(float),
                vol.Optional("ramp_a_per_min", default=opts.get("ramp_a_per_min", DEFAULT_RAMP_A_PER_MIN)): vol.Coerce(float),
                vol.Optional("min_up_interval_s", default=opts.get("min_up_interval_s", DEFAULT_MIN_UP_INTERVAL_S)): int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


async def async_get_options_flow(config_entry):
    return OptionsFlowHandler(config_entry)
