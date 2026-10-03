"""Simple synchronous throttle. No Django dependencies."""
import time


class Throttle:
    """Sleep just enough between calls to stay under X calls/minute."""

    def __init__(self, calls_per_minute: int):
        if calls_per_minute <= 0:
            raise ValueError("calls_per_minute must be > 0")
        self._min_interval = 60.0 / calls_per_minute
        self._last_call_ts = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last_call_ts
        remaining = self._min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_call_ts = time.monotonic()