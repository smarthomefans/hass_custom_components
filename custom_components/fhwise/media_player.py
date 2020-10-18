"""The implementation of fhwise media player."""
import logging

from datetime import timedelta
import voluptuous as vol
import traceback

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import (
    MEDIA_TYPE_MUSIC,
    SUPPORT_TURN_ON,
    SUPPORT_TURN_OFF,
    SUPPORT_CLEAR_PLAYLIST,
    SUPPORT_NEXT_TRACK,
    SUPPORT_PAUSE,
    SUPPORT_PLAY,
    SUPPORT_PREVIOUS_TRACK,
    SUPPORT_SEEK,
    SUPPORT_SELECT_SOUND_MODE,
    SUPPORT_SELECT_SOURCE,
    SUPPORT_SHUFFLE_SET,
    SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET,
    SUPPORT_VOLUME_STEP,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    STATE_OFF,
    STATE_PAUSED,
    STATE_PLAYING,
)
from homeassistant.exceptions import PlatformNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
import homeassistant.util.dt as dt_util
from .const import (
    DOMAIN,
    FHWISE_OBJECT,
)
from fhwise import FhwisePlayer

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "fh wise media player"
DEFAULT_PORT = 8080

PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA_BASE.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)

ATTR_MODEL = "model"
ATTR_AREA = "area"
MODEL_WLBM209 = "WISE-WLBM209-FLS101"
SUPPORT_4_AREA_MODELS = [MODEL_WLBM209]

SUPPORT_AREA_MODELS = SUPPORT_4_AREA_MODELS

SOUND_MODE_NORMAL = "Normal"
SOUND_MODE_ROCK = "Rock"
SOUND_MODE_POP = "Pop"
SOUND_MODE_DANCE = "Dance"
SOUND_MODE_HIPHOP = "HipHop"
SOUND_MODE_CLASSIC = "Classic"
SOUND_MODE_BASS = "Bass"
SOUND_MODE_VOICE = "Voice"
SOUND_MODE_OFF = "Off"
# Do not change order
SOUND_MODE_LIST = [
    SOUND_MODE_NORMAL,  # 0
    SOUND_MODE_ROCK,  # 1
    SOUND_MODE_POP,  # 2
    SOUND_MODE_DANCE,  # 3
    SOUND_MODE_HIPHOP,  # 4
    SOUND_MODE_CLASSIC,  # 5
    SOUND_MODE_BASS,  # 6
    SOUND_MODE_VOICE,  # 7
    SOUND_MODE_OFF,
]
DEFAULT_SOUND_MODE = SOUND_MODE_OFF

SOURCE_LOCAL = "Local"
SOURCE_LINE_IN_1 = "Line in 1"
SOURCE_LINE_IN_2 = "Line in 2"
SOURCE_BLUETOOTH = "Bluetooth"
SOURCE_UX = "Radio"
# Do not change order
SOURCE_LIST = [
    SOURCE_LOCAL,  # 0
    SOURCE_LINE_IN_1,  # 1
    SOURCE_LINE_IN_2,  # 2
    SOURCE_BLUETOOTH,  # 3
    SOURCE_UX,
]
DEFAULT_SOURCE = SOURCE_LOCAL

PLAY_MODE_SEQ = "Sequence"
PLAY_MODE_REPEAT_ALL = "Repeat All"
PLAY_MODE_REPEAT_ONE = "Repeat One"
PLAY_MODE_RANDOM = "Random"
# Do not change order
PLAY_MODE_LIST = [
    PLAY_MODE_SEQ,  # 0
    PLAY_MODE_REPEAT_ALL,  # 1
    PLAY_MODE_REPEAT_ONE,  # 2
    PLAY_MODE_RANDOM,  # 3
]
DEFAULT_PLAY_MODE = PLAY_MODE_SEQ

MUSIC_PLAYER_SUPPORT = (
    SUPPORT_PAUSE
    | SUPPORT_VOLUME_SET
    | SUPPORT_VOLUME_MUTE
    | SUPPORT_TURN_ON
    | SUPPORT_TURN_OFF
    | SUPPORT_CLEAR_PLAYLIST
    | SUPPORT_SEEK
    | SUPPORT_SELECT_SOURCE
    | SUPPORT_PLAY
    | SUPPORT_SHUFFLE_SET
    | SUPPORT_VOLUME_STEP
    | SUPPORT_PREVIOUS_TRACK
    | SUPPORT_NEXT_TRACK
    | SUPPORT_SELECT_SOUND_MODE
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the fhwise platform."""

    port = config[CONF_PORT]
    host = config[CONF_HOST]
    name = config[CONF_NAME]
    devices = []
    fhPlayer = FhwisePlayer(host, port)
    _LOGGER.info(f"Initializing with {host}:{port}")

    try:
        fhPlayer.connect()
        model = fhPlayer.send_heartbeat()
        fhPlayer.disconnect()
        _LOGGER.info(f"{model} detected")
    except Exception as err:
        _LOGGER.error(f"Error connecting to fhwise at {host}:{port}")
        raise PlatformNotReady from err

    fhPlayerDevice = FhwiseMusicPlayerDevice(fhPlayer, host, port, model)
    await fhPlayerDevice.async_update()
    async_track_time_interval(
        hass, fhPlayerDevice.async_update, timedelta(seconds=5)
    )

    devices.append(FhwiseMusicPlayer(fhPlayerDevice, name))
    for i in range(fhPlayerDevice.supported_area_num):
        devices.append(FhwiseMusicPlayer(fhPlayerDevice, name, i+1))

    async_add_entities(devices, update_before_add=True)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the fhwise platform."""
    port = config_entry.data[CONF_PORT]
    host = config_entry.data(CONF_HOST)
    name = config_entry.data(CONF_NAME)
    devices = []

    fhPlayer = hass.data[DOMAIN][config_entry.entry_id][FHWISE_OBJECT]

    model = fhPlayer.send_heartbeat()

    fhPlayerDevice = FhwiseMusicPlayerDevice(fhPlayer, host, port, model)
    await fhPlayerDevice.async_update()
    async_track_time_interval(
        hass, fhPlayerDevice.async_update, timedelta(seconds=5)
    )

    devices.append(FhwiseMusicPlayer(fhPlayerDevice, name))
    for i in range(fhPlayerDevice.supported_area_num):
        devices.append(FhwiseMusicPlayer(fhPlayerDevice, name, i+1))

    async_add_entities(devices, update_before_add=True)


class FhwiseMusicPlayerDevice:
    """A fhwise media player that only supports music."""

    tracks = []

    def __init__(self, player, host, port, model):
        """Initialize the demo device."""
        self._player = player
        self._host = host
        self._port = port
        self._model = model

        self._player_state = STATE_PAUSED
        self._available = False
        self._play_mode = DEFAULT_PLAY_MODE
        self._sound_mode = DEFAULT_SOUND_MODE
        self._source = DEFAULT_SOURCE
        self._cur_track = 0
        self._cur_track_pos = 0
        self._cur_track_len = 0
        self._cur_area_name = ""
        self._cur_area_id = ""
        self._volume_muted = False
        self._media_position_updated_at = None

        self._area_state = {}

    @property
    def supported_area(self):
        """Docstring."""
        return self._model in SUPPORT_AREA_MODELS

    @property
    def supported_area_num(self):
        """Docstring."""
        if self._model in SUPPORT_4_AREA_MODELS:
            return 4
        return 0

    @property
    def unique_id(self):
        """Docstring."""
        return f"{self._model}-{self._host}"

    @property
    def model(self):
        """Docstring."""
        return self._model

    @property
    def available(self):
        """Docstring."""
        return self._available

    @property
    def shuffle(self):
        """Docstring."""
        return self._play_mode is PLAY_MODE_RANDOM

    @property
    def sound_mode(self):
        """Docstring."""
        return self._sound_mode

    @property
    def source(self):
        """Docstring."""
        return self._source

    @property
    def current_track(self):
        """Docstring."""
        return self._cur_track

    @property
    def current_track_position(self):
        """Docstring."""
        return int(self._cur_track_pos / 1000)

    @property
    def current_track_length(self):
        """Docstring."""
        return int(self._cur_track_len / 1000)

    @property
    def media_position_updated_at(self):
        """Last valid time of media position."""
        return self._media_position_updated_at

    @property
    def current_title(self):
        """Return the title of current playing media."""
        return self.tracks[self._cur_track][1] if self.tracks else ""

    @property
    def current_artist(self):
        """Return the artist of current playing media (Music track only)."""
        return self.tracks[self._cur_track][0] if self.tracks else ""

    @property
    def current_area_id(self):
        """Docstring."""
        return self._cur_area_id

    @property
    def area_state(self):
        """Docstring."""
        return self._area_state

    @property
    def play_state(self):
        """Docstring."""
        return self._player_state

    @property
    def muted(self):
        """Docstring."""
        return self._volume_muted

    async def _try_command(self, mask_error, func, *args, **kwargs):
        """Call a player command handling error messages."""
        try:
            # result = await self.hass.async_add_executor_job(
            #    partial(func, *args, **kwargs)
            # )
            result = func(*args, **kwargs)
            _LOGGER.debug(f"Response received from player: {result}")
            return result
        except Exception:
            _LOGGER.error(mask_error)
            self._available = False
            raise Exception

    async def async_set_play_mode(self, mode):
        """Docstring."""
        if mode not in PLAY_MODE_LIST:
            _LOGGER.error(f"play mode {mode} not support")
            return

        result = await self._try_command(
            "Get play mode failed", self._player.get_play_mode
        )
        if PLAY_MODE_LIST[result] == mode:
            return

        while True:
            result = await self._try_command(
                "Toggle play mode failed", self._player.set_toggle_play_mode
            )
            if PLAY_MODE_LIST[result] == mode:
                return

    async def async_set_shuffle(self, shuffle):
        """Enable/disable shuffle mode."""
        mode = PLAY_MODE_RANDOM if shuffle else PLAY_MODE_SEQ
        await self.async_set_play_mode(mode)
        self._play_mode = mode

    async def async_mute_volume(self, mute):
        """Mute the volume."""
        if self._volume_muted != mute:
            await self._try_command(
                "Mute the player failed.", self._player.set_volume_toggle_mute
            )
            self._volume_muted = mute

    async def async_set_volume_level(self, volume, area_id):
        """Set the volume level, range 0..1."""
        if area_id == "0":
            result = await self._try_command(
                "Set volume level failed.",
                self._player.set_volume_level,
                int(volume),
            )
            _LOGGER.debug(result)
            if volume != 0 and result == 0:
                # Maybe muted, un-mute and set again
                _LOGGER.debug("Call set volume but resule still 0. Try un-mute.")
                await self.async_mute_volume(False)
                await self._try_command(
                    "Set volume level failed.",
                    self._player.set_volume_level,
                    int(volume),
                )
            self._area_state[area_id]["volume"] = int(volume)
        else:
            result = await self._try_command(
                "Set sub area failed.",
                self._player.set_sub_area_control,
                int(area_id) - 1,
                int(volume),
                self._area_state[area_id]["state"],
            )
            _LOGGER.debug(result)
            if volume != 0 and int(result.split("::")[1]) == 0:
                # Maybe muted, un-mute and set again
                _LOGGER.debug("Call set volume but resule still 0. Try un-mute.")
                await self.async_mute_volume(False)
                await self._try_command(
                    "Set sub area failed.",
                    self._player.set_sub_area_control,
                    int(area_id) - 1,
                    int(volume),
                    self._area_state[area_id]["state"],
                )
            self._area_state[area_id]["volume"] = int(volume)

    async def async_media_play_pause(self):
        """Send play command."""
        await self._try_command(
            "Turning the player play failed.", self._player.send_play_pause
        )
        if self._player_state != STATE_PLAYING:
            self._player_state = STATE_PLAYING
        else:
            self._player_state = STATE_PAUSED

    async def async_media_on_off(self, area_id):
        """Send on/off command."""
        if area_id == "0":
            _LOGGER.info(f"{self._model} dose not support area, can not turn off.")
            return await self.async_media_play_pause()
        else:
            await self._try_command(
                "Set sub area failed.",
                self._player.set_sub_area_control,
                int(area_id) - 1,
                self._area_state[area_id]["volume"],
                not self._area_state[area_id]["state"],
            )
            self._area_state[area_id]["state"] = not self._area_state[area_id]["state"]

    async def async_media_set_track(self, track_id):
        """Send previous track command."""
        await self._try_command(
            "Set track failed.", self._player.set_current_list_play_file, track_id
        )
        self._cur_track = track_id

    async def async_media_seek(self, position):
        """Send seek command."""
        await self._try_command(
            "Set seek failed.", self._player.set_current_file_position, position * 1000
        )
        self._cur_track_pos = position * 1000
        self._media_position_updated_at = dt_util.utcnow()

    async def async_select_sound_mode(self, sound_mode):
        """Select sound mode."""
        if sound_mode not in SOUND_MODE_LIST:
            _LOGGER.error(f"{sound_mode} is not support.")
            return

        if sound_mode == SOUND_MODE_OFF:
            await self._try_command(
                "Turn off EQ switch failed.", self._player.set_eq_switch, 0
            )
        else:
            await self._try_command(
                "Turn on EQ switch failed.", self._player.set_eq_switch, 1
            )
            await self._try_command(
                "Set EQ switch failed.",
                self._player.set_eq_type,
                SOUND_MODE_LIST.index(sound_mode),
            )
        self._sound_mode = sound_mode

    async def async_select_source(self, source):
        """Select input source."""
        if source not in SOURCE_LIST:
            _LOGGER.error(f"{source} is not support.")
            return

        await self._try_command(
            "Set source failed.",
            self._player.set_volume_source,
            SOURCE_LIST.index(source),
        )
        self._source = source

    async def async_update(self, *args, **kwargs):
        """Fetch state from the device."""
        try:
            if self.supported_area:
                room_info = (
                    await self._try_command(
                        "Get current room info failed.",
                        self._player.get_current_room_info,
                    )
                ).split("::")
                _LOGGER.debug(f"Got current room info: {room_info}")
                self._cur_area_name = room_info[0]
                self._cur_area_id = room_info[1]


            volume_level = await self._try_command(
                "Get volume level failed", self._player.get_volume_level
            )
            _LOGGER.debug(f"Got new vol level: {volume_level}")
            self._area_state["0"] = {"volume": int(volume_level), "state": True}

            if self.supported_area:
                for i in range(self.supported_area_num):
                    area_info = (
                        await self._try_command(
                            "Get area info failed.",
                            self._player.get_sub_area_control,
                            i,
                        )
                    ).split("::")
                    _LOGGER.debug(f"Got area info: {area_info}")
                    self._area_state[f"{int(area_info[0])+1}"] = {
                        "volume": int(area_info[1]),
                        "state": area_info[2] != "0",
                    }

            play_state = await self._try_command(
                "Get play status failed.", self._player.get_play_status
            )
            _LOGGER.debug(f"Got state: {play_state}")
            if play_state == 1:
                self._player_state = STATE_PLAYING
            elif play_state == 2:
                self._player_state = STATE_PAUSED

            self._volume_muted = True
            for (_, v) in self._area_state.items():
                if v["state"] and v["volume"] > 0:
                    self._volume_muted = False
                    break

            cur_eq_switch = await self._try_command(
                "Get current EQ switch failed", self._player.get_eq_switch
            )
            _LOGGER.debug(f"Got current EQ switch: {cur_eq_switch}")
            if cur_eq_switch:
                cur_eq_mode = await self._try_command(
                    "Get current EQ mode failed", self._player.get_eq_type
                )
                _LOGGER.debug(f"Got current EQ mode: {cur_eq_mode}")
                self._sound_mode = SOUND_MODE_LIST[cur_eq_mode]
            else:
                self._sound_mode = SOUND_MODE_OFF

            cur_source_id = await self._try_command(
                "Get current source failed", self._player.get_volume_source
            )
            _LOGGER.debug(f"Got current source: {cur_source_id}")
            self._source = SOURCE_LIST[cur_source_id]

            cur_list_tracks_account = await self._try_command(
                "Get current list tracks account failed",
                self._player.get_current_list_file_account,
            )
            _LOGGER.debug(f"Got current list tracks account: {cur_list_tracks_account}")

            cur_track_name = await self._try_command(
                "Get current list tracks name failed",
                self._player.get_current_file_name,
            )
            _LOGGER.debug(f"Got current list tracks name: {cur_track_name}")

            self.tracks = []
            for i in range(cur_list_tracks_account):
                """
                    info:
                    0::Eagles-加州旅馆::432067::<unknown>::/mnt/internal_sd/Music/华尔思内存/Eagles-加州旅馆.wav
                """
                info = await self._try_command(
                    "Get list tracks account failed",
                    self._player.get_current_list_file_info,
                    i,
                )
                _LOGGER.debug(f"Got list [{i}] tracks info: {info}")
                info_array = info.split("::")
                _LOGGER.debug(f"Got info array: {info_array}")
                self.tracks.append((info_array[3], info_array[1]))
                if info_array[1] == cur_track_name:
                    _LOGGER.debug(f"Got current track number: {i}")
                    self._cur_track = i
                    self._cur_track_len = int(info_array[2])

            cur_track_pos = await self._try_command(
                "Get current track position failed",
                self._player.get_current_file_position,
            )
            _LOGGER.debug(f"Got current track position: {cur_track_pos}ms")
            if self._cur_track_pos != cur_track_pos:
                self._cur_track_pos = cur_track_pos
                self._media_position_updated_at = dt_util.utcnow()

            cur_play_mode = await self._try_command(
                "Get current play mode failed", self._player.get_play_mode
            )
            self._play_mode = PLAY_MODE_LIST[cur_play_mode]

            self._available = True

        except Exception as err:
            self._available = False
            _LOGGER.error(f"Got exception while fetching device state")
            _LOGGER.error(err)
            traceback.print_exc()


class FhwiseMusicPlayer(MediaPlayerEntity):
    """A fhwise media player that only supports music."""

    tracks = []

    def __init__(self, player_dev, name, area=0):
        """Initialize the demo device."""
        self._player_dev = player_dev
        self._area = f"{area}"
        if area:
            self._name = f"{name} {area}"
            self._unique_id = f"{self._player_dev.unique_id}-{area}"
            self._state_attrs = {ATTR_MODEL: self._player_dev.model, ATTR_AREA: self._area}
        else:
            self._name = f"{name}"
            self._unique_id = f"{self._player_dev.unique_id}"
            self._state_attrs = {ATTR_MODEL: self._player_dev.model}

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return MUSIC_PLAYER_SUPPORT

    @property
    def media_content_type(self):
        """Return the content type of current playing media."""
        return MEDIA_TYPE_MUSIC

    @property
    def should_poll(self):
        """Push an update after each command."""
        return True

    @property
    def unique_id(self):
        """Return an unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the media player."""
        return self._name

    @property
    def available(self):
        """Return true when state is known."""
        return self._player_dev.available

    @property
    def device_state_attributes(self):
        """Return the state attributes of the device."""
        return self._state_attrs

    @property
    def state(self):
        """Return the state of the player."""
        if not self._player_dev.area_state[self._area]["state"]:
            return STATE_OFF
        return self._player_dev.play_state

    @property
    def volume_level(self):
        """Return the volume level of the media player (0..1)."""
        return self._player_dev.area_state[self._area]["volume"] * 0.0666

    @property
    def is_volume_muted(self):
        """Return boolean if volume is currently muted."""
        return self._player_dev.muted

    @property
    def shuffle(self):
        """Boolean if shuffling is enabled."""
        return self._player_dev.shuffle

    @property
    def sound_mode(self):
        """Return the current sound mode."""
        return self._player_dev.sound_mode

    @property
    def sound_mode_list(self):
        """Return a list of available sound modes."""
        return SOUND_MODE_LIST

    @property
    def source(self):
        """Return name of the current input source."""
        return self._player_dev.source

    @property
    def source_list(self):
        """Return a list of available input sources."""
        return SOURCE_LIST

    @property
    def media_duration(self):
        """Return the duration of current playing media in seconds."""
        return self._player_dev.current_track_length

    @property
    def media_position(self):
        """Position of current playing media in seconds."""
        return self._player_dev.current_track_position

    @property
    def media_position_updated_at(self):
        """Last valid time of media position."""
        return self._player_dev.media_position_updated_at

    @property
    def media_title(self):
        """Return the title of current playing media."""
        return self._player_dev.current_title

    @property
    def media_artist(self):
        """Return the artist of current playing media (Music track only)."""
        return self._player_dev.current_artist

    @property
    def media_track(self):
        """Return the track number of current media (Music track only)."""
        return self._player_dev.current_track

    async def async_turn_on(self):
        """Turn the media player on."""
        if self.state is STATE_OFF:
            await self._player_dev.async_media_on_off(self._area)
        if self.state is not STATE_PLAYING:
            await self._player_dev.async_media_play_pause()
        self.schedule_update_ha_state()

    async def async_turn_off(self):
        """Turn the media player off."""
        if self.state is not STATE_OFF:
            await self._player_dev.async_media_on_off(self._area)
        self.schedule_update_ha_state()

    async def async_mute_volume(self, mute):
        """Mute the volume."""
        await self._player_dev.async_set_volume_level(0, self._area)
        self.schedule_update_ha_state()

    async def async_volume_up(self):
        """Increase volume."""
        volume = self._player_dev.area_state[self._area]["volume"]
        volume = min(15, volume + 1)
        await self._player_dev.async_set_volume_level(volume, self._area)
        self.schedule_update_ha_state()

    async def async_volume_down(self):
        """Decrease volume."""
        volume = self._player_dev.area_state[self._area]["volume"]
        volume = max(0, volume - 1)
        await self._player_dev.async_set_volume_level(volume, self._area)
        self.schedule_update_ha_state()

    async def async_set_volume_level(self, volume):
        """Set the volume level, range 0..1."""
        volume_level = int(volume / 0.0666)
        await self._player_dev.async_set_volume_level(volume_level, self._area)
        self.schedule_update_ha_state()

    async def async_media_play(self):
        """Send play command."""
        await self.async_turn_on()
        if self.state is not STATE_PLAYING:
            await self._player_dev.async_media_play_pause()
        self.schedule_update_ha_state()

    async def async_media_pause(self):
        """Send pause command."""
        await self.async_turn_on()
        if self.state is STATE_PLAYING:
            await self._player_dev.async_media_play_pause()
        self.schedule_update_ha_state()

    async def async_media_previous_track(self):
        """Send previous track command."""
        track = self._player_dev.current_track
        if track > 0:
            await self._player_dev.async_media_set_track(track - 1)
        self.schedule_update_ha_state()

    async def async_media_next_track(self):
        """Send next track command."""
        track = self._player_dev.current_track
        if track < len(self._player_dev.tracks) - 1:
            await self._player_dev.async_media_set_track(track + 1)
        self.schedule_update_ha_state()

    async def async_media_seek(self, position):
        """Send seek command."""
        await self._player_dev.async_media_seek(position)
        self.schedule_update_ha_state()

    async def async_select_sound_mode(self, sound_mode):
        """Select sound mode."""
        await self._player_dev.async_select_sound_mode(sound_mode)
        self.schedule_update_ha_state()

    async def async_select_source(self, source):
        """Select input source."""
        await self._player_dev.async_select_source(source)
        self.schedule_update_ha_state()

    async def async_set_shuffle(self, shuffle):
        """Enable/disable shuffle mode."""
        await self._player_dev.async_set_shuffle(shuffle)
        self.schedule_update_ha_state()

    async def async_update(self):
        """Docstring."""
        return
