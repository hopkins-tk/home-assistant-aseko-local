"""Server for receiving and parsing Aseko unit data."""

import logging
from datetime import datetime, time

import homeassistant.util

from .aseko_data import (
    AsekoDevice,
    AsekoDeviceType,
    AsekoElectrolyzerDirection,
    AsekoProbeType,
)
from .const import (
    ELECTROLYZER_RUNNING,
    ELECTROLYZER_RUNNING_LEFT,
    MESSAGE_SIZE,
    PROBE_CLF,
    PROBE_REDOX,
    PUMP_RUNNING,
    WATER_FLOW_TO_PROBES,
    YEAR_OFFSET,
)

_LOGGER = logging.getLogger(__name__)


class AsekoDecoder:
    """Decoder of Aseko unit data."""

    @staticmethod
    def _unit_type(
        data: bytes,
    ) -> AsekoDeviceType:
        """Determine the unit type from the binary data."""

        if len(data) == MESSAGE_SIZE:
            probe_info = data[4]
            has_redox_probe = bool(probe_info & PROBE_REDOX)
            has_clf_probe = bool(probe_info & PROBE_CLF)

            if has_redox_probe and has_clf_probe:
                return AsekoDeviceType.PROFI

            if data[20] or data[21]:
                return AsekoDeviceType.SALT

            return AsekoDeviceType.HOME

        return AsekoDeviceType.NET

    @staticmethod
    def _available_probes(
        data: bytes,
    ) -> list[AsekoProbeType]:
        """Determine types of probes installed from the binary data."""

        probe_info = data[4]
        has_redox_probe = bool(probe_info & PROBE_REDOX)
        has_clf_probe = bool(probe_info & PROBE_CLF)

        probes = [AsekoProbeType.PH]
        if has_redox_probe:
            probes.append(AsekoProbeType.REDOX)
        if has_clf_probe:
            probes.append(AsekoProbeType.CLF)

        return probes

    @staticmethod
    def _timestamp(
        data: bytes,
    ) -> datetime:
        """Decode datetime from the bynary data."""

        return datetime(
            year=YEAR_OFFSET + data[6],
            month=data[7],
            day=data[8],
            hour=data[9],
            minute=data[10],
            second=data[11],
            tzinfo=homeassistant.util.dt.get_default_time_zone(),
        )

    @staticmethod
    def _electrolyzer_direction(
        data: bytes,
    ) -> AsekoElectrolyzerDirection | None:
        """Decode electrolyzer direction from the bynary data."""

        if (data[29] & ELECTROLYZER_RUNNING_LEFT) == ELECTROLYZER_RUNNING_LEFT:
            return AsekoElectrolyzerDirection.LEFT
        if data[29] & ELECTROLYZER_RUNNING:
            return AsekoElectrolyzerDirection.RIGHT
        return AsekoElectrolyzerDirection.WAITING

    @staticmethod
    def _fill_ph_data(
        unit: AsekoDevice,
        data: bytes,
    ) -> None:
        unit.ph = int.from_bytes(data[14:16], "big") / 100
        unit.required_ph = data[52] / 10

    @staticmethod
    def _fill_redox_data(
        unit: AsekoDevice,
        data: bytes,
    ) -> None:
        unit.redox = int.from_bytes(data[18:20], "big")
        unit.required_redox = data[53] * 10

    @staticmethod
    def _fill_clf_data(
        unit: AsekoDevice,
        data: bytes,
    ) -> None:
        unit.cl_free = int.from_bytes(data[16:18], "big") / 100
        unit.required_cl_free = data[53] / 10

    @staticmethod
    def _fill_salt_unit_data(
        unit: AsekoDevice,
        data: bytes,
    ) -> None:
        if data[21]:
            unit.salinity = data[20] / 10
            unit.electrolyzer_power = data[21] if data[29] & ELECTROLYZER_RUNNING else 0
            unit.electrolyzer_active = bool(data[29] & ELECTROLYZER_RUNNING)
            unit.electrolyzer_direction = AsekoDecoder._electrolyzer_direction(data)

    @staticmethod
    def decode(data: bytes) -> AsekoDevice:
        """Decode 120-byte array into AsekoData."""

        unit_type = AsekoDecoder._unit_type(data)
        probes = AsekoDecoder._available_probes(data)

        device = AsekoDevice(
            serial_number=int.from_bytes(data[0:4], "big"),
            type=unit_type,
            timestamp=AsekoDecoder._timestamp(data),
            water_temperature=int.from_bytes(data[25:27], "big") / 10,
            water_flow_to_probes=(data[28] == WATER_FLOW_TO_PROBES),
            pump_running=bool(data[29] & PUMP_RUNNING),
            required_algicide=data[54],
            required_temperature=data[55],
            start1=time(hour=data[56], minute=data[57]),
            stop1=time(hour=data[58], minute=data[59]),
            start2=time(hour=data[60], minute=data[61]),
            stop2=time(hour=data[62], minute=data[63]),
            backwash_every_n_days=data[68],
            backwash_time=time(hour=data[69], minute=data[70]),
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

        return device
