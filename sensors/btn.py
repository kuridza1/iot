import time
import threading
from typing import Callable

def run_button_loop(
    delay_sec: float,
    read_fn: Callable[[], bool],
    callback: Callable[[bool], None],
    stop_event: threading.Event,
) -> None:
    last = None
    while not stop_event.is_set():
        v = bool(read_fn())
        if last is None or v != last:
            callback(v)
            last = v
        time.sleep(delay_sec)