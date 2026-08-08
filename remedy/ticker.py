from __future__ import annotations

import threading
import time
from contextlib import contextmanager


@contextmanager
def ticking(label: str, interval: float = 1.0):
    """Prints elapsed time every `interval` seconds while the wrapped call
    is in flight -- so a slow API call doesn't look like a hang."""
    stop = threading.Event()

    def tick():
        start = time.time()
        while not stop.wait(interval):
            print(f"\r{label}... {time.time() - start:.0f}s", end="", flush=True)

    thread = threading.Thread(target=tick, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=interval + 0.5)
        print(f"\r{label}... done{' ' * 10}")
