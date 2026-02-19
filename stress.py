# ============================================================================
# IDM Test - Stress Test Module
# Safe CPU stress for POS hardware maintenance testing
# ============================================================================

import threading
import time
import math


class StressEngine:
    """Lightweight CPU stress generator safe for POS hardware."""

    def __init__(self):
        self._running = False
        self._threads: list[threading.Thread] = []
        self._mode = "idle"

    @property
    def mode(self) -> str:
        return self._mode

    def start_idle(self):
        self._mode = "idle"

    def start_load(self):
        self._mode = "load"
        self._running = True
        num_workers = max(1, (threading.active_count() // 2) or 1)
        import psutil
        num_workers = max(1, min(2, psutil.cpu_count(logical=False) or 2))

        for _ in range(num_workers):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            self._threads.append(t)

    def _worker(self):
        """Moderate CPU workload with periodic sleep to avoid overheating."""
        while self._running:
            end = time.monotonic() + 0.3
            while time.monotonic() < end:
                math.factorial(800)
                math.sqrt(999999.9)
                _ = [x * x for x in range(500)]
            time.sleep(0.2)

    def stop(self):
        self._running = False
        self._mode = "idle"
        for t in self._threads:
            t.join(timeout=2)
        self._threads.clear()
