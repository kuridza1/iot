import random
import threading
import time
from typing import Callable, Tuple


def run_gyro_loop(delay: float,
                  callback_xyz: Callable[[Tuple[float, float, float]], None],
                  movement_cb: Callable[[float], None],
                  stop_event: threading.Event,
                  movement_threshold: float = 80.0,
                  cooldown_sec: float = 3.0) -> None:
    gx = gy = gz = 0.0
    last_alarm = 0.0

    while not stop_event.is_set():
        gx += random.uniform(-6.0, 6.0)
        gy += random.uniform(-6.0, 6.0)
        gz += random.uniform(-6.0, 6.0)

        gx = max(-250.0, min(250.0, gx))
        gy = max(-250.0, min(250.0, gy))
        gz = max(-250.0, min(250.0, gz))

        callback_xyz((round(gx, 2), round(gy, 2), round(gz, 2)))

        mag = (gx*gx + gy*gy + gz*gz) ** 0.5
        now = time.time()
        if mag >= movement_threshold and (now - last_alarm) >= cooldown_sec:
            last_alarm = now
            movement_cb(float(round(mag, 2)))

        time.sleep(delay)
