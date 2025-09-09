import logging
from datetime import datetime, time
from enum import IntEnum
import homeassistant.util


from .aseko_data import (
    AsekoDevice,
    AsekoDeviceType,
    AsekoElectrolyzerDirection,
    AsekoProbeType,
    AsekoPumpType,
)
from .const import (
    ELECTROLYZER_RUNNING,
    ELECTROLYZER_RUNNING_LEFT,
    PROBE_CLF_MISSING,
    PROBE_DOSE_MISSING,
    PROBE_REDOX_MISSING,
    PROBE_SANOSIL_MISSING,
    PUMP_RUNNING,
    UNSPECIFIED_VALUE,
    WATER_FLOW_TO_PROBES,
    YEAR_OFFSET,
)

_LOGGER = logging.getLogger(__name__)


class AsekoDecoder:
    """Decoder of Aseko unit data."""

    @staticmethod
    def _normalize_value(value: int | str | None) -> int | str | None:
        """Normalize raw values to None if they are unspecified/invalid.

        Rules:
        - None stays None
        - Integer 255 (0xFF) → None
        - Empty string "" → None
        - String "255" → None
        - Otherwise: return value unchanged
        """
        if value is None:
            return None

        if isinstance(value, int):
            return None if value == UNSPECIFIED_VALUE else value

        if isinstance(value, str):
            val = value.strip()
            if not val or val == str(UNSPECIFIED_VALUE):
                return None
            return val

        return value

    @staticmethod
    def _unit_type(data: bytes) -> AsekoDeviceType | None:
        """Determine the Aseko device type. Returns None until a reliable detection is possible."""

        # 1. Serial number must be valid (first 4 bytes, big endian)
        serial = int.from_bytes(data[0:4], "big")
        if not serial or serial in (0, UNSPECIFIED_VALUE, 0xFFFFFFFF):
            _LOGGER.debug("Unit type detection skipped: invalid serial (%s)", serial)
            return None

        # 2. NET devices always report byte[6] = 0xFF
        if data[6] == UNSPECIFIED_VALUE:
            _LOGGER.debug("Unit type detected: NET (byte[6] = 0xFF)")
            return AsekoDeviceType.NET

        # 3. Check available probes
        probe_info = AsekoDecoder._available_probes(data)

        if AsekoProbeType.REDOX in probe_info and AsekoProbeType.CLF in probe_info:
            _LOGGER.debug("Unit type detected: PROFI (probes include REDOX and CLF)")
            return AsekoDeviceType.PROFI

        # 4. SALT only if data[20]/data[21] have valid values
        if (
            (data[20] or data[21])
            and AsekoProbeType.SANOSIL not in probe_info
            and AsekoProbeType.DOSE not in probe_info
        ):
            _LOGGER.debug(
                "Unit type detected: SALT (valid values in data[20]/[21], probes=%s)",
                probe_info,
            )
            return AsekoDeviceType.SALT

        # 5. HOME as fallback if probes exist
        if probe_info:
            _LOGGER.debug("Unit type detected: HOME (fallback, probes=%s)", probe_info)
            return AsekoDeviceType.HOME

        # 6. Nothing clear yet → wait for more data
        _LOGGER.debug("Unit type not yet determined, waiting for more data...")
        return None

    @staticmethod
    def _available_probes(data: bytes) -> set[AsekoProbeType]:
        probe_info = data[4]
        probes = {AsekoProbeType.PH}

        if not bool(probe_info & PROBE_REDOX_MISSING):
            probes.add(AsekoProbeType.REDOX)
        if not bool(probe_info & PROBE_CLF_MISSING):
            probes.add(AsekoProbeType.CLF)
        if not bool(probe_info & PROBE_SANOSIL_MISSING):
            probes.add(AsekoProbeType.SANOSIL)
        if not bool(probe_info & PROBE_DOSE_MISSING):
            probes.add(AsekoProbeType.DOSE)

        return probes

    @staticmethod
    def _timestamp(data: bytes) -> datetime | None:
        tz = homeassistant.util.dt.get_default_time_zone()

        if len(data) < 12 or data[6] == UNSPECIFIED_VALUE:
            return datetime.now(tz=tz)

        try:
            year = YEAR_OFFSET + data[6]
            month = min(max(data[7], 1), 12)
            day = min(max(data[8], 1), 31)
            hour = min(max(data[9], 0), 23)
            minute = min(max(data[10], 0), 59)
            second = min(max(data[11], 0), 59)

            return datetime(
                year=year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                second=second,
                tzinfo=tz,
            )
        except ValueError as e:
            _LOGGER.warning(
                "Received invalid timestamp (%s) – falling back to now(). Frame: %s",
                e,
                data.hex(),
            )
            return datetime.now(tz=tz)

    @staticmethod
    def _time(data: bytes) -> time | None:
        if data[0] == UNSPECIFIED_VALUE:
            return None

        hour = data[0]
        minute = data[1]

        if not (0 <= hour <= 23):
            hour = 0
        if not (0 <= minute <= 59):
            minute = 0

        try:
            return time(hour=hour, minute=minute)
        except ValueError as e:
            _LOGGER.warning("Invalid time in frame (%s) – data=%s", e, data.hex())
            return None

    @staticmethod
    def _electrolyzer_direction(data: bytes) -> AsekoElectrolyzerDirection | None:
        if (data[29] & ELECTROLYZER_RUNNING_LEFT) == ELECTROLYZER_RUNNING_LEFT:
            return AsekoElectrolyzerDirection.LEFT
        if data[29] & ELECTROLYZER_RUNNING:
            return AsekoElectrolyzerDirection.RIGHT
        return AsekoElectrolyzerDirection.WAITING

    @staticmethod
    def _fill_ph_data(unit: AsekoDevice, data: bytes) -> None:
        unit.ph = int.from_bytes(data[14:16], "big") / 100
        unit.required_ph = data[52] / 10

    @staticmethod
    def _fill_redox_data(unit: AsekoDevice, data: bytes) -> None:
        if data[18] == UNSPECIFIED_VALUE and data[19] == UNSPECIFIED_VALUE:
            unit.redox = int.from_bytes(data[16:18], "big")
        else:
            unit.redox = int.from_bytes(data[18:20], "big")
        unit.required_redox = data[53] * 10

    @staticmethod
    def _fill_clf_data(unit: AsekoDevice, data: bytes) -> None:
        unit.cl_free = int.from_bytes(data[16:18], "big") / 100
        unit.required_cl_free = data[53] / 10
        unit.cl_free_mv = int.from_bytes(data[20:22], "big")

    @staticmethod
    def _fill_salt_unit_data(unit: AsekoDevice, data: bytes) -> None:
        unit.salinity = data[20] / 10
        unit.electrolyzer_power = data[21] if data[29] & ELECTROLYZER_RUNNING else 0
        unit.electrolyzer_active = bool(data[29] & ELECTROLYZER_RUNNING)
        unit.electrolyzer_direction = AsekoDecoder._electrolyzer_direction(data)

    @staticmethod
    def _fill_flowrate_data(unit: AsekoDevice, data: bytes) -> None:
        def _normalize(value: int) -> int | None:
            return None if value == 255 else value

        unit.flowrate_chlor = _normalize(data[95])
        unit.flowrate_ph_plus = _normalize(data[97])
        unit.flowrate_ph_minus = _normalize(data[99])
        unit.flowrate_floc = _normalize(data[101])

    @staticmethod
    def decode(data: bytes) -> AsekoDevice:
        unit_type = AsekoDecoder._unit_type(data)
        probes = AsekoDecoder._available_probes(data)
        normalize = AsekoDecoder._normalize_value

        ts = AsekoDecoder._timestamp(data)
        _LOGGER.debug("Decoded timestamp = %s (raw: %s)", ts, data[6:12].hex())

        # Pumpe
        pump_code = int(data[29])
        active_pump = (
            AsekoPumpType(pump_code)
            if pump_code in AsekoPumpType._value2member_map_
            else AsekoPumpType.OFF
        )

        device = AsekoDevice(
            serial_number=int.from_bytes(data[0:4], "big"),
            device_type=unit_type,
            timestamp=AsekoDecoder._timestamp(data),
            water_temperature=int.from_bytes(data[25:27], "big") / 10,
            water_flow_to_probes=(data[28] == WATER_FLOW_TO_PROBES),
            pump_running=bool(data[29] & PUMP_RUNNING),
            active_pump=active_pump,
            required_algicide=data[54],
            required_water_temperature=normalize(data[55]),
            start1=AsekoDecoder._time(data[56:58]),
            stop1=AsekoDecoder._time(data[58:60]),
            start2=AsekoDecoder._time(data[60:62]),
            stop2=AsekoDecoder._time(data[62:64]),
            backwash_every_n_days=data[68],
            backwash_time=AsekoDecoder._time(data[69:71]),
            backwash_duration=data[71] * 10,
            pool_volume=int.from_bytes(data[92:94], "big"),
            max_filling_time=int.from_bytes(data[94:96], "big"),
            delay_after_startup=int.from_bytes(data[74:76], "big"),
            delay_after_dose=int.from_bytes(data[106:108], "big"),
        )

        if AsekoProbeType.PH in probes:
            AsekoDecoder._fill_ph_data(device, data)
        if AsekoProbeType.REDOX in probes:
            AsekoDecoder._fill_redox_data(device, data)
        if AsekoProbeType.CLF in probes:
            AsekoDecoder._fill_clf_data(device, data)
        if unit_type in (AsekoDeviceType.SALT, AsekoDeviceType.PROFI):
            AsekoDecoder._fill_salt_unit_data(device, data)

        AsekoDecoder._fill_flowrate_data(device, data)

        return device
