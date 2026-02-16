import random
import time
from typing import Callable


def run_dht_loop(
    delay: float,
    temp_c_start: float,
    hum_pct_start: float,
    callback: Callable[[float, float], None],
    stop_event,
) -> None:
    """@brief Simulated DHT: small random walk for temperature/humidity."""
    temp = float(temp_c_start)
    hum = float(hum_pct_start)

    while not stop_event.is_set():
        temp += random.uniform(-0.2, 0.2)
        hum += random.uniform(-0.8, 0.8)

        temp = max(10.0, min(35.0, temp))
        hum = max(15.0, min(85.0, hum))

        callback(round(temp, 1), round(hum, 1))
        time.sleep(delay)
