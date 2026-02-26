import threading
from typing import Optional, Tuple


class FourDigitTimer:
    def __init__(self, simulated: bool = True) -> None:
        self.simulated = simulated
        self._running = False
        self._seconds_left = 0
        self._blink = False
        self._blink_on = True
        self._lock = threading.Lock()


    def set(self, seconds: int) -> None:
        with self._lock:
            self._seconds_left = max(0, int(seconds))
            self._blink = False

    def start(self) -> None:
        with self._lock:
            if self._seconds_left > 0:
                self._running = True

    def stop(self) -> None:
        with self._lock:
            self._running = False

    def reset(self) -> None:
        with self._lock:
            self._running = False
            self._seconds_left = 0
            self._blink = False
            self._blink_on = True

    def status(self) -> Tuple[bool, int]:
        with self._lock:
            return self._running, self._seconds_left


    def add(self, seconds: int) -> None:
        with self._lock:
            self._seconds_left = max(0, self._seconds_left + int(seconds))

    def stop_blink(self) -> None:
        with self._lock:
            self._blink = False
            self._blink_on = True

    def is_blinking(self) -> bool:
        with self._lock:
            return self._blink
        
    def tick_1hz(self) -> tuple[Optional[int], bool]:
        with self._lock:
            finished_now = False

            if self._running and self._seconds_left > 0:
                self._seconds_left -= 1
                if self._seconds_left == 0:
                    self._running = False
                    self._blink = True
                    self._blink_on = True
                    finished_now = True
                return self._seconds_left, finished_now

            if self._blink:
                self._blink_on = not self._blink_on
                return 0, False

            return None, False

    def render(self) -> str:
        with self._lock:
            if self._blink:
                return "00:00" if self._blink_on else "    "
            sec = self._seconds_left

        mm = sec // 60
        ss = sec % 60
        return f"{mm:02d}:{ss:02d}"
