"""Server for receiving and parsing Aseko unit data."""

from datetime import datetime, time
import logging

from .aseko_data import (
    AsekoDevice,
    AsekoDeviceType,
    AsekoElectrolyzerDirection,
    AsekoProbeType,
)
from .const import YEAR_OFFSET

_LOGGER = logging.getLogger(__name__)


class AsekoDecoder:
    """Decoder of Aseko unit data."""

    @staticmethod
    def _unit_type(
        data: bytes,
    ) -> AsekoDeviceType:
        """Determine the unit type from the binary data."""

        return AsekoDeviceType.SALT

    @staticmethod
    def _available_probes(
        deviceType: AsekoDeviceType,
        data: bytes,
    ) -> list[AsekoProbeType]:
        """Determine types of probes installed from the binary data."""
        match deviceType:
            case AsekoDeviceType.PROFI:
                return [AsekoProbeType.PH, AsekoProbeType.REDOX, AsekoProbeType.CL]
            case AsekoDeviceType.SALT:
                # Can be either CL or REDOX (REDOX is used typically)
                return [AsekoProbeType.PH, AsekoProbeType.REDOX]
            case AsekoDeviceType.HOME:
                # Can be either CL or REDOX or OXY (CL is used typically)
                return [AsekoProbeType.PH, AsekoProbeType.CL]
            case AsekoDeviceType.NET:
                # Can be either CL or REDOX (REDOX is used typically)
                return [AsekoProbeType.PH, AsekoProbeType.REDOX]

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
        )

    @staticmethod
    def _electrolyzer_direction(
        data: bytes,
    ) -> AsekoElectrolyzerDirection | None:
        """Decode electrolyzer direction from the bynary data."""

        if (data[29] & 0x50) == 0x50:
            return AsekoElectrolyzerDirection.LEFT
        if data[29] & 0x10:
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
    def _fill_cl_data(
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
        unit.electrolyzer_power = data[21] if data[29] & 0x10 else 0
        unit.electrolyzer_active = bool(data[29] & 0x10)
        unit.electrolyzer_direction = AsekoDecoder._electrolyzer_direction(data)

    @staticmethod
    def decode(data: bytes) -> AsekoDevice:
        """Decode 120-byte array into AsekoData."""

        unitType = AsekoDecoder._unit_type(data)
        probeTypes = AsekoDecoder._available_probes(unitType, data)

        unitData = AsekoDevice(
            serial_number=int.from_bytes(data[0:4], "big"),
            type=unitType,
            timestamp=AsekoDecoder._timestamp(data),
            water_temperature=int.from_bytes(data[25:27], "big") / 10,
            water_flow_to_probes=(data[28] == 0xAA),
            pump_running=bool(data[29] & 0x08),
            required_algicide=data[54],
            required_temperature=data[55],
            start1=time(hour=data[56], minute=data[57]),
            stop1=time(hour=data[58], minute=data[59]),
            start2=time(hour=data[60], minute=data[61]),
            stop2=time(hour=data[62], minute=data[63]),
            pool_volume=int.from_bytes(data[92:94], "big"),
            max_filling_time=int.from_bytes(data[94:96], "big"),
        )

        if AsekoProbeType.PH in probeTypes:
            AsekoDecoder._fill_ph_data(unitData, data)

        if AsekoProbeType.REDOX in probeTypes:
            AsekoDecoder._fill_redox_data(unitData, data)

        if AsekoProbeType.CL in probeTypes:
            AsekoDecoder._fill_cl_data(unitData, data)

        if unitType == AsekoDeviceType.SALT:
            AsekoDecoder._fill_salt_unit_data(unitData, data)

        return unitData
