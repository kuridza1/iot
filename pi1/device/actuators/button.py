from dataclasses import dataclass
from device.helper import GPIO


@dataclass
class Button:
    """
    @brief Button input
    Behaves as a trigger
    """
    simulated: bool
    pin: int
    active_high: bool = True

    def __post_init__(self) -> None:
        self._state = False
        if not self.simulated:
            GPIO.setup_in(self.pin)

    def isOn(self):
        if self._state == False:
            return False
        return True

    def on(self) -> None:
        self._set(True)

    def off(self) -> None:
        self._set(False)

    def _set(self, on: bool) -> None:
        self._state = on
        if self.simulated or not GPIO.available:
            return
        value = on if self.active_high else (not on)
        GPIO.output(self.pin, value)


    def cleanup(self) -> None:
        pass
