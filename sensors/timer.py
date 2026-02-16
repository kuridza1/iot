import threading
import time
from typing import Callable, Optional, Tuple

from actuators.four_digit_timer import FourDigitTimer


def run_timer_loop(timer: FourDigitTimer,
                   callback: Callable[[str, int], None],
                   finished_cb: Callable[[], None],
                   stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        rem, finished_now = timer.tick_1hz()
        if rem is not None:
            callback(timer.render(), rem)
        if finished_now:
            finished_cb()
        time.sleep(1.0)
