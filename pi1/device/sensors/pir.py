import random
import time
from typing import Callable


def run_pir_loop(delay: float, callback: Callable[[bool], None], stop_event) -> None:
    """@brief Simulated PIR that randomly triggers motion bursts."""
    motion = False
    burst_left = 0
    while not stop_event.is_set():
        if burst_left <= 0 and random.random() < 0.15:
            burst_left = random.randint(2, 6)
            motion = True
            callback(True)
        elif burst_left > 0:
            burst_left -= 1
            if burst_left == 0 and motion:
                motion = False
                callback(False)
        time.sleep(delay)