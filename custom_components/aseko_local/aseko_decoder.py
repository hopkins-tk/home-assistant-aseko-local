import logging
from datetime import datetime, time
import homeassistant.util
from typing import Type, TypeVar


from .aseko_data import (
    AsekoActuatorMasks,
    AsekoDevice,
    AsekoDeviceType,
    AsekoElectrolyzerDirection,
    AsekoProbeType,
    ACTUATOR_MASKS,
)
from .const import (
    ALGICIDE_CONFIGURED,
    PROBE_CLF_MISSING,
    PROBE_DOSE_MISSING,
    PROBE_REDOX_MISSING,
    PROBE_SANOSIL_MISSING,
    UNIT_TYPE_HOME,
    UNIT_TYPE_NET,
    UNIT_TYPE_PROFI,
    UNIT_TYPE_SALT,
    UNSPECIFIED_VALUE,
    WATER_FLOW_TO_PROBES,
    YEAR_OFFSET,
)

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


class AsekoDecoder:
    """Decoder of Aseko unit data."""

    @staticmethod
    def _normalize_value(value: int | str | None, type: Type[T]) -> T | None:
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

        if type is int and isinstance(value, int):
            return None if value == UNSPECIFIED_VALUE else type(value)

        if type is str and isinstance(value, str):
            val = value.strip()
            if not val or val == str(UNSPECIFIED_VALUE):
                return None
            return type(val)

        raise ValueError(f"Unsupported type {type} or value {value}")

    @staticmethod
    def _unit_type(data: bytes) -> AsekoDeviceType | None:
        """Determine the Aseko device type. Returns None until a reliable detection is possible."""

        if data[4] == UNIT_TYPE_PROFI:
            return AsekoDeviceType.PROFI

        if (data[4] & UNIT_TYPE_SALT) == UNIT_TYPE_SALT:
            return AsekoDeviceType.SALT

        if (data[4] & UNIT_TYPE_HOME) == UNIT_TYPE_HOME:
            return AsekoDeviceType.HOME

        if bool(data[4] & UNIT_TYPE_NET):
            return AsekoDeviceType.NET

        error = f"Unknown unit type: {data[4]}"
        _LOGGER.warning(error)
        raise ValueError(error)

    @staticmethod
    def _configuration(data: bytes) -> set[AsekoProbeType]:
        """Determine types of probes installed from the binary data."""

        probe_info = data[4]

        probes = set()
        probes.add(AsekoProbeType.PH)

        if (
            not bool(probe_info & PROBE_REDOX_MISSING)
            or (data[4] & UNIT_TYPE_HOME) == UNIT_TYPE_HOME
        ):
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
        """Extract timestamp from data and validates timestamp."""

        if (
            len(data) < 12
            or data[6] == UNSPECIFIED_VALUE
            or data[7] == UNSPECIFIED_VALUE
            or data[8] == UNSPECIFIED_VALUE
            or data[9] == UNSPECIFIED_VALUE
            or data[10] == UNSPECIFIED_VALUE
            or data[11] == UNSPECIFIED_VALUE
        ):
            _LOGGER.info(
                "Received unspecified timestamp – falling back to now(). Frame: %s",
                data.hex(),
            )
            return datetime.now(tz=homeassistant.util.dt.get_default_time_zone())

        try:
            year = YEAR_OFFSET + data[6]

            month = data[7]
            day = data[8]
            hour = data[9]
            minute = data[10]
            second = data[11]

            return datetime(
                year=year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                second=second,
                tzinfo=homeassistant.util.dt.get_default_time_zone(),
            )

        except ValueError as e:
            _LOGGER.warning(
                "Received invalid timestamp (%s) – falling back to now(). Frame: %s",
                e,
                data.hex(),
            )
            return datetime.now(tz=homeassistant.util.dt.get_default_time_zone())

    @staticmethod
    def _time(data: bytes) -> time | None:
        if data[0] == UNSPECIFIED_VALUE:
            return None

        hour = data[0]
        minute = data[1]

        try:
            return time(hour=hour, minute=minute)
        except ValueError as e:
            _LOGGER.warning("Invalid time in frame (%s) – data=%s", e, data.hex())
            return None

    @staticmethod
    def _electrolyzer_direction(
        data: bytes, masks: AsekoActuatorMasks
    ) -> AsekoElectrolyzerDirection:
        if (
            masks.electrolyzer_running_left
            and (data[29] & masks.electrolyzer_running_left)
            == masks.electrolyzer_running_left
        ):
            return AsekoElectrolyzerDirection.LEFT
        if (
            masks.electrolyzer_running_right
            and data[29] & masks.electrolyzer_running_right
        ):
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

        if unit.device_type != AsekoDeviceType.PROFI:
            unit.required_redox = data[53] * 10
        else:
            unit.required_redox = None

    @staticmethod
    def _fill_clf_data(unit: AsekoDevice, data: bytes) -> None:
        unit.cl_free = int.from_bytes(data[16:18], "big") / 100
        unit.required_cl_free = data[53] / 10
        if unit.device_type != AsekoDeviceType.SALT:
            unit.cl_free_mv = int.from_bytes(data[20:22], "big")

    @staticmethod
    def _fill_salt_unit_data(unit: AsekoDevice, data: bytes) -> None:
        masks = ACTUATOR_MASKS[AsekoDeviceType.SALT]
        unit.salinity = data[20] / 10
        unit.electrolyzer_power = (
            data[21] if data[29] & masks.electrolyzer_running else 0
        )
        unit.electrolyzer_active = bool(data[29] & masks.electrolyzer_running)
        unit.electrolyzer_direction = AsekoDecoder._electrolyzer_direction(data, masks)

    @staticmethod
    def _fill_flowrate_data(unit: AsekoDevice, data: bytes) -> None:
        # Bytes 95 and 99 are unconditional: pH− pump and Cl pump.
        unit.flowrate_ph_minus = AsekoDecoder._normalize_value(data[95], int)
        unit.flowrate_chlor = AsekoDecoder._normalize_value(data[99], int)
        # byte[101]: shared "third pump slot" — algicide OR flocculant per byte[37].
        # bit 0x10 in byte[37] = algicide (ml/m³/day); not set = flocculant (ml/h).
        # 0xFF (UNSPECIFIED) → configuration unknown → leave both as None.
        if data[37] != UNSPECIFIED_VALUE and bool(data[37] & ALGICIDE_CONFIGURED):
            unit.flowrate_algicide = AsekoDecoder._normalize_value(data[101], int)
        elif data[37] != UNSPECIFIED_VALUE:
            unit.flowrate_floc = AsekoDecoder._normalize_value(data[101], int)
        # flowrate_ph_plus (byte 97): mapping unconfirmed

    @staticmethod
    def _fill_consumable_data(unit: AsekoDevice, data: bytes) -> None:
        masks = ACTUATOR_MASKS.get(unit.device_type)
        if masks is None:
            _LOGGER.warning("No actuator masks for device type %s", unit.device_type)
            return

        if masks.filtration:
            unit.filtration_pump_running = bool(data[29] & masks.filtration)

        if masks.cl:
            unit.cl_pump_running = bool(data[29] & masks.cl)

        if masks.ph_minus:
            unit.ph_minus_pump_running = bool(data[29] & masks.ph_minus)

        # Algicide and flocculant share bit 0x20 on some device types and byte 37
        # (ALGICIDE_CONFIGURED) is unreliable (0xFF = unspecified) on several devices.
        # Instead, use flowrate presence (non-0xFF in the respective flowrate byte) as
        # the pump-existence discriminator. _fill_flowrate_data must run first.
        if masks.algicide and unit.flowrate_algicide is not None:
            unit.algicide_pump_running = bool(data[29] & masks.algicide)

        if masks.flocculant and unit.flowrate_floc is not None:
            unit.floc_pump_running = bool(data[29] & masks.flocculant)

    @staticmethod
    def decode(data: bytes) -> AsekoDevice:
        unit_type = AsekoDecoder._unit_type(data)
        probes = AsekoDecoder._configuration(data)

        ts = AsekoDecoder._timestamp(data)
        _LOGGER.debug("Decoded timestamp = %s (raw: %s)", ts, data[6:12].hex())

        device = AsekoDevice(
            serial_number=int.from_bytes(data[0:4], "big"),
            device_type=unit_type,
            configuration=probes,
            timestamp=AsekoDecoder._timestamp(data),
            water_temperature=int.from_bytes(data[25:27], "big") / 10,
            water_flow_to_probes=(data[28] == WATER_FLOW_TO_PROBES),
            required_algicide=AsekoDecoder._normalize_value(data[54], int)
            if data[37] != UNSPECIFIED_VALUE and bool(data[37] & ALGICIDE_CONFIGURED)
            else None,
            required_floc=AsekoDecoder._normalize_value(data[54], int)
            if data[37] != UNSPECIFIED_VALUE
            and not bool(data[37] & ALGICIDE_CONFIGURED)
            else None,
            required_water_temperature=AsekoDecoder._normalize_value(data[55], int),
            start1=AsekoDecoder._time(data[56:58]),
            stop1=AsekoDecoder._time(data[58:60]),
            start2=AsekoDecoder._time(data[60:62]),
            stop2=AsekoDecoder._time(data[62:64]),
            backwash_every_n_days=AsekoDecoder._normalize_value(data[68], int),
            backwash_time=AsekoDecoder._time(data[69:71]),
            backwash_duration=data[71] * 10 if data[71] != UNSPECIFIED_VALUE else None,
            pool_volume=int.from_bytes(data[92:94], "big"),
            max_filling_time=int.from_bytes(data[94:96], "big"),
            delay_after_startup=int.from_bytes(data[74:76], "big"),
            delay_after_dose=int.from_bytes(data[106:108], "big"),
        )

        if AsekoProbeType.PH in device.configuration:
            AsekoDecoder._fill_ph_data(device, data)
        if AsekoProbeType.REDOX in device.configuration:
            AsekoDecoder._fill_redox_data(device, data)
        if AsekoProbeType.CLF in device.configuration:
            AsekoDecoder._fill_clf_data(device, data)
        if unit_type == AsekoDeviceType.SALT:
            AsekoDecoder._fill_salt_unit_data(device, data)

        # Flowrate must be decoded before consumable data: pump presence for
        # algicide/flocculant is determined by whether the flowrate byte is set (≠ 0xFF).
        AsekoDecoder._fill_flowrate_data(device, data)
        AsekoDecoder._fill_consumable_data(device, data)

        return device
