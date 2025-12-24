import random
import time
from typing import Callable


def run_button_loop(delay: float, callback: Callable[[bool], None], stop_event) -> None:
    """@brief Simulated button that randomly toggles."""
    pressed = False
    while not stop_event.is_set():
        if random.random() < 0.2:
            pressed = not pressed
            callback(pressed)
        time.sleep(delay)

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
