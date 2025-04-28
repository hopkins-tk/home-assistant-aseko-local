"""Server for receiving and parsing Aseko unit data."""

import asyncio
from collections.abc import Awaitable, Callable
import logging

from .aseko_data import AsekoData, AsekoDevice
from .aseko_decoder import AsekoDecoder
from .const import MESSAGE_SIZE

_LOGGER = logging.getLogger(__name__)


class AsekoDeviceServer:
    """Async TCP server for receiving and parsing Aseko unit data."""

    _instances: dict[str, "AsekoDeviceServer"] = {}

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 47524,
        on_data: Callable[[AsekoDevice], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize the server."""
        self.host = host
        self.port = port
        self.on_data = on_data
        self._server: asyncio.AbstractServer | None = None

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

        return self._server is not None and self._server.is_serving()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle incoming client connection."""

        addr = writer.get_extra_info("peername")

        _LOGGER.debug("Connection from %s", addr)

        try:
            byteData = await reader.readexactly(MESSAGE_SIZE)
            device = AsekoDecoder.decode(byteData)

            _LOGGER.debug("Received data from %s: %s", addr, byteData.hex())
            _LOGGER.debug("Received data parsed as %s", device)

            if self.on_data:
                self.on_data(device)
        except asyncio.IncompleteReadError:
            _LOGGER.debug("Connection from %s closed", addr)
        finally:
            writer.close()
            await writer.wait_closed()

    @classmethod
    async def create(
        cls,
        host: str = "0.0.0.0",
        port: int = 47524,
        on_data: Callable[[AsekoData], Awaitable[None]] | None = None,
    ) -> "AsekoDeviceServer":
        """Get or create an instance of AsekoUnitServer for the given host and port."""

        key = f"{host}:{port}"
        if key not in cls._instances:
            cls._instances[key] = AsekoDeviceServer(host, port, on_data)
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
