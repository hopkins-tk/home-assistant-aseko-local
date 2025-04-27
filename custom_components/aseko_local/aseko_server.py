"""Server for receiving and parsing Aseko unit data."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, time
import logging

from .aseko_data import (
    AsekoData,
    AsekoDeviceType,
    AsekoElectrolyzerDirection,
    AsekoProbeType,
    AsekoUnitData,
)
from .const import MESSAGE_SIZE, YEAR_OFFSET

_LOGGER = logging.getLogger(__name__)


class AsekoUnitServer:
    """Async TCP server for receiving and parsing Aseko unit data."""

    _instances: dict[str, "AsekoUnitServer"] = {}

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 47524,
        on_data: Callable[[AsekoUnitData], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the server."""
        self.host = host
        self.port = port
        self.on_data = on_data
        self._server: asyncio.AbstractServer | None = None
        self._data = AsekoData()

    async def start(self) -> None:
        """Start the TCP server."""

        try:
            self._server = await asyncio.start_server(
                self._handle_client, self.host, self.port
            )

            _LOGGER.info("AsekoUnitServer started on %s:%d", self.host, self.port)
        except OSError as err:
            _LOGGER.error("Failed to start AsekoUnitServer: %s", err)

            raise ServerConnectionError(f"Failed to start server: {err}") from err

    async def stop(self) -> None:
        """Stop the TCP server."""

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

            _LOGGER.info("AsekoUnitServer stopped")

    @property
    def running(self) -> bool:
        """Check if the server is running."""

        return self._server is not None and not self._server.is_closing()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle incoming client connection."""

        addr = writer.get_extra_info("peername")

        _LOGGER.debug("Connection from %s", addr)

        try:
            byteData = await reader.readexactly(MESSAGE_SIZE)
            aseko_unit_data = self.decode(byteData)
            self._data.set(aseko_unit_data.serial_number, aseko_unit_data)

            _LOGGER.debug("Received data from %s: %s", addr, byteData.hex())
            _LOGGER.debug("Received data parsed as %s", aseko_unit_data)

            if self.on_data:
                self.on_data(aseko_unit_data)
        except asyncio.IncompleteReadError:
            _LOGGER.debug("Connection from %s closed", addr)
        finally:
            writer.close()
            await writer.wait_closed()

    @staticmethod
    def _determine_unit_type(
        data: bytes,
    ) -> AsekoDeviceType:
        """Determine the unit type from the binary data."""

        return AsekoDeviceType.SALT

    @staticmethod
    def _determine_probes(
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
    def _decode_timestamp(
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
    def _decode_electrolyzer_direction(
        data: bytes,
    ) -> AsekoElectrolyzerDirection | None:
        """Decode electrolyzer direction from the bynary data."""

        if data[29] & 0x50:
            return AsekoElectrolyzerDirection.LEFT
        if data[29] & 0x10:
            return AsekoElectrolyzerDirection.RIGHT
        return AsekoElectrolyzerDirection.WAITING

    @staticmethod
    def decode(data: bytes) -> AsekoUnitData:
        """Decode received 120-byte array into AsekoData."""

        unitType = AsekoUnitServer._determine_unit_type(data)
        probeTypes = AsekoUnitServer._determine_probes(unitType, data)

        unitData = AsekoUnitData(
            serial_number=int.from_bytes(data[0:4], "big"),
            type=unitType,
            timestamp=AsekoUnitServer._decode_timestamp(data),
            water_temperature=int.from_bytes(data[25:27], "big") / 10,
            water_flow_to_probes=bool(data[28] & 0xAA),
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
            unitData.ph = int.from_bytes(data[14:16], "big") / 100
            unitData.required_ph = data[52] / 10
        if AsekoProbeType.REDOX in probeTypes:
            unitData.redox = int.from_bytes(data[18:20], "big")
            unitData.required_redox = data[53] * 10
        if AsekoProbeType.CL in probeTypes:
            unitData.cl_free = int.from_bytes(data[16:18], "big") / 100
            unitData.required_cl_free = data[53] / 10

        if unitType == AsekoDeviceType.SALT:
            unitData.salinity = data[20] / 10
            unitData.electrolyzer_power = data[21] if data[29] & 0x10 else 0
            unitData.electrolyzer_active = bool(data[29] & 0x10)
            unitData.electrolyzer_direction = (
                AsekoUnitServer._decode_electrolyzer_direction(data)
            )

        return unitData

    @classmethod
    async def create(
        cls,
        host: str = "0.0.0.0",
        port: int = 47524,
        on_data: Callable[[AsekoData], Awaitable[None]] | None = None,
    ) -> "AsekoUnitServer":
        """Get or create an instance of AsekoUnitServer for the given host and port."""

        key = f"{host}:{port}"
        if key not in cls._instances:
            cls._instances[key] = AsekoUnitServer(host, port, on_data)
            await cls._instances[key].start()

        return cls._instances[key]

    @classmethod
    async def remove(cls, host: str, port: int) -> None:
        """Remove an instance of AsekoUnitServer for the given host and port."""

        key = f"{host}:{port}"
        if key in cls._instances:
            if cls._instances[key] is not None:
                await cls._instances[key].stop()
                del cls._instances[key]


class ServerConnectionError(Exception):
    """Exception class for connection error."""
