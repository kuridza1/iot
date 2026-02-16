import random
import time
from typing import Callable


_IR_CODES = [
    "POWER",
    "OFF",
    "R",
    "G",
    "B",
    "YELLOW",
    "CYAN",
    "MAGENTA",
    "WHITE",
]


def run_ir_loop(
    delay: float,
    burst_prob: float,
    callback: Callable[[str], None],
    stop_event,
) -> None:
    """@brief Simulated IR receiver: occasionally emits a remote-control code."""
    while not stop_event.is_set():
        if random.random() < float(burst_prob):
            code = random.choice(_IR_CODES)
            callback(code)
        time.sleep(delay)
