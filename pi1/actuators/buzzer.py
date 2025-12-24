from dataclasses import dataclass
import time

from helper import GPIO


@dataclass
class Buzzer:
    """@brief Buzzer actuator (real GPIO or simulated)."""
    simulated: bool
    pin: int
    active_high: bool = True

    def __post_init__(self) -> None:
        self._state = False
        if not self.simulated:
            GPIO.setup_out(self.pin)

    def on(self) -> None:
        self._set(True)

    def off(self) -> None:
        self._set(False)

    def isOn(self):
        if self._state == False:
            return False
        else:
            return True
        
    def beep(self, seconds: float = 0.2) -> None:
        time.sleep(max(0.0, float(seconds)))

    def _set(self, on: bool) -> None:
        self._state = on
        if self.simulated or not GPIO.available:
            return
        value = on if self.active_high else (not on)
        GPIO.output(self.pin, value)

    def cleanup(self) -> None:
        pass

