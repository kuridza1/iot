import random
import time
from typing import Callable


def run_ultrasonic_loop(delay: float, callback: Callable[[float], None], stop_event) -> None:
    """@brief Simulated ultrasonic distance (cm) using small random walk with occasional close object."""
    distance = 120.0
    while not stop_event.is_set():
        if random.random() < 0.1:
            distance = random.uniform(10.0, 40.0)
        else:
            distance += random.uniform(-8.0, 8.0)
            distance = min(200.0, max(5.0, distance))
        callback(round(distance, 1))
        time.sleep(delay)
