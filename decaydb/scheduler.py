"""TheSNMC RustDB background scheduler loop for periodic decay ticks."""

from __future__ import annotations

import threading
import time

from decaydb.engine import DecayEngine


class DecayScheduler:
    def __init__(
        self, engine: DecayEngine, tenant_id: str = "default", interval_sec: float = 2.0, shadow_mode: bool = False
    ):
        self.engine = engine
        self.tenant_id = tenant_id
        self.interval_sec = interval_sec
        self.shadow_mode = shadow_mode
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.engine.decay_tick(tenant_id=self.tenant_id, shadow_mode=self.shadow_mode)
            time.sleep(self.interval_sec)

