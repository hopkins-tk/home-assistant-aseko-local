import os
import datetime
import logging

_LOGGER = logging.getLogger(__name__)

class LoggingHelper:
    """Central logging helper for Aseko integration with persistent file handles."""

    def __init__(self, log_dir: str, raw_log_enabled: bool):
        self.log_dir = log_dir
        self.raw_log_enabled = raw_log_enabled
        self._files = {}
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        try:
            os.makedirs(self.log_dir, exist_ok=True)
        except Exception as e:
            _LOGGER.error("Could not create log directory %s: %s", self.log_dir, e)

    def _open_file(self, name: str, mode: str):
        """Open file if not already open, store handle."""
        if name not in self._files:
            path = os.path.join(self.log_dir, name)
            try:
                self._files[name] = open(path, mode)
                _LOGGER.debug("Opened log file: %s", path)
            except Exception as e:
                _LOGGER.error("Failed to open log file %s: %s", path, e)
        return self._files.get(name)

    def log_hex_frame(self, frame: bytes):
        if not self.raw_log_enabled:
            return
        fh = self._open_file("mirror_hex.log", "a")
        if fh:
            fh.write(f"{datetime.datetime.now().isoformat()} {frame.hex()}\n")
            fh.flush()

    def log_bin_frame(self, frame: bytes):
        if not self.raw_log_enabled:
            return
        fh = self._open_file("mirror_bin.log", "ab")
        if fh:
            fh.write(frame)
            fh.flush()

    def log_flowrates(self, source: str, device):
        if not self.raw_log_enabled:
            return
        fh = self._open_file("flowrates.log", "a")
        if fh:
            fh.write(
                f"{datetime.datetime.now().isoformat()} [{source}] "
                f"FlowRates: ChlorPure={device.flow_rates.chlor_pure}, "
                f"pHMinus={device.flow_rates.ph_minus}, "
                f"pHPlus={device.flow_rates.ph_plus}, "
                f"FlocPlusC={device.flow_rates.floc_plus_c}\n"
            )
            fh.flush()

    def log_info(self, source: str, message: str):
        if not self.raw_log_enabled:
            return
        fh = self._open_file("info.log", "a")
        if fh:
            fh.write(f"{datetime.datetime.now().isoformat()} [{source}] {message}\n")
            fh.flush()

    def log_raw_packet(self, source: str, frame: bytes):
        """General raw packet logging to raw_frames.log."""
        if not self.raw_log_enabled:
            return
        fh = self._open_file("raw_frames.log", "ab")
        if fh:
            fh.write(frame + b"\n")
            fh.flush()

    def close(self):
        """Close all open log files."""
        for name, fh in self._files.items():
            try:
                fh.close()
                _LOGGER.debug("Closed log file: %s", name)
            except Exception:
                pass
        self._files.clear()
