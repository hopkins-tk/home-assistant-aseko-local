import os
import datetime
import logging
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class LoggingHelper:
    """Central logging helper for Aseko integration with persistent file handles (async safe)."""

    def __init__(self, hass: HomeAssistant, log_dir: str, raw_log_enabled: bool):
        self.hass = hass
        self.log_dir = log_dir
        self.raw_log_enabled = raw_log_enabled
        self._files: dict[str, any] = {}
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        try:
            os.makedirs(self.log_dir, exist_ok=True)
        except Exception as e:
            _LOGGER.error("Could not create log directory %s: %s", self.log_dir, e)

    async def _open_file(self, name: str, mode: str):
        """Open file if not already open, store handle (async safe)."""
        if name not in self._files:
            path = os.path.join(self.log_dir, name)
            try:
                self._files[name] = await self.hass.async_add_executor_job(
                    open, path, mode
                )
                _LOGGER.debug("Opened log file: %s", path)
            except Exception as e:
                _LOGGER.error("Failed to open log file %s: %s", path, e)
                return None
        return self._files.get(name)

    async def log_hex_frame(self, frame: bytes):
        if not self.raw_log_enabled:
            return
        fh = await self._open_file("mirror_hex.log", "a")
        if fh:
            await self.hass.async_add_executor_job(
                fh.write, f"{datetime.datetime.now().isoformat()} {frame.hex()}\n"
            )
            await self.hass.async_add_executor_job(fh.flush)

    async def log_bin_frame(self, frame: bytes):
        if not self.raw_log_enabled:
            return
        fh = await self._open_file("mirror_bin.log", "ab")
        if fh:
            await self.hass.async_add_executor_job(fh.write, frame)
            await self.hass.async_add_executor_job(fh.flush)

    async def log_flowrates(self, source: str, device):
        if not self.raw_log_enabled:
            return
        fh = await self._open_file("flowrates.log", "a")
        if fh:
            line = (
                f"{datetime.datetime.now().isoformat()} [{source}] "
                f"FlowRates: ChlorPure={device.flow_rates.chlor}, "
                f"pHMinus={device.flow_rates.ph_minus}, "
                f"pHPlus={device.flow_rates.ph_plus}, "
                f"FlocPlusC={device.flow_rates.floc}\n"
            )
            await self.hass.async_add_executor_job(fh.write, line)
            await self.hass.async_add_executor_job(fh.flush)

    async def log_info(self, source: str, message: str, log: bool = False):
        if not self.raw_log_enabled and not log:
            return
        fh = await self._open_file("info.log", "a")
        if fh:
            line = f"{datetime.datetime.now().isoformat()} [{source}] {message}\n"
            await self.hass.async_add_executor_job(fh.write, line)
            await self.hass.async_add_executor_job(fh.flush)

    async def log_raw_packet(self, source: str, frame: bytes):
        """General raw packet logging to raw_frames.log."""
        if not self.raw_log_enabled:
            return
        fh = await self._open_file("raw_frames.log", "ab")
        if fh:
            await self.hass.async_add_executor_job(fh.write, frame + b"\n")
            await self.hass.async_add_executor_job(fh.flush)

    async def async_close(self):
        """Close all open log files asynchronously."""
        for name, fh in list(self._files.items()):
            try:
                await self.hass.async_add_executor_job(fh.close)
                _LOGGER.debug("Closed log file: %s", name)
            except Exception:
                pass
        self._files.clear()
