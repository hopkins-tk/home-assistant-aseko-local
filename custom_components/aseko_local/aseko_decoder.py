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
    def _unit_type(
        data: bytes,
    ) -> AsekoDeviceType:
        """Determine the unit type from the binary data."""

        if data[6] != UNSPECIFIED_VALUE:
            probe_info = AsekoDecoder._available_probes(data)

            if AsekoProbeType.REDOX in probe_info and AsekoProbeType.CLF in probe_info:
                return AsekoDeviceType.PROFI

            if (
                (data[20] or data[21])
                and AsekoProbeType.SANOSIL not in probe_info
                and AsekoProbeType.DOSE not in probe_info
            ):
                return AsekoDeviceType.SALT

            return AsekoDeviceType.HOME

        return AsekoDeviceType.NET

    @staticmethod
    def _available_probes(
        data: bytes,
    ) -> set[AsekoProbeType]:
        """Determine types of probes installed from the binary data."""

        probe_info = data[4]

        probes = set()
        probes.add(AsekoProbeType.PH)

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
    def _timestamp(
        data: bytes,
    ) -> datetime | None:
        """Decode datetime from the bynary data."""

        if data[6] != UNSPECIFIED_VALUE:
            return datetime(
                year=YEAR_OFFSET + data[6],
                month=data[7],
                day=data[8],
                hour=data[9],
                minute=data[10],
                second=data[11],
                tzinfo=homeassistant.util.dt.get_default_time_zone(),
            )

        return datetime.now(
            tz=homeassistant.util.dt.get_default_time_zone(),
        )

    @staticmethod
    def _time(
        data: bytes,
    ) -> time | None:
        """Decode time from the bynary data."""

        return (
            time(
                hour=data[0],
                minute=data[1],
            )
            if data[0] != UNSPECIFIED_VALUE
            else None
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
        if data[18] == UNSPECIFIED_VALUE and data[19] == UNSPECIFIED_VALUE:
            unit.redox = int.from_bytes(data[16:18], "big")
        else:
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

        return device
