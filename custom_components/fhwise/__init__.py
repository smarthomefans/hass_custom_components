"""The fhwise player component."""
import logging
from fhwise import FhwisePlayer

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    FHWISE_OBJECT,
)

PLATFORMS = ["media_player"]

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the fhwise component."""
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    _LOGGER.error("in async setup")
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=deepcopy(conf)
        )
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up fhwise from a config entry."""
    port = entry.data[CONF_PORT]
    host = entry.data(CONF_HOST)
    name = entry.data(CONF_NAME)
    fhPlayer = FhwisePlayer(host, port)
    _LOGGER.info(f"Initializing with {host}:{port}")

    try:
        fhPlayer.connect()
        model = fhPlayer.send_heartbeat()
        fhPlayer.disconnect()
        _LOGGER.info(f"{model} detected")
    except Exception as err:
        _LOGGER.error(f"Error connecting to fhwise at {host}:{port}")
        raise ConfigEntryNotReady from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        FHWISE_OBJECT: monoprice,
        FHWISE_MODEL: model
    }

    for component in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
