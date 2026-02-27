from dataclasses import dataclass
from helper.helper import GPIO


@dataclass
class Button:
    simulated: bool
    pin: int
    active_high: bool = True
    pull: str = "down"  

    def __post_init__(self) -> None:
        self._sim_state = False 

        if not self.simulated:
            GPIO.setup_in(self.pin, pull=self.pull)

    def isOn(self) -> bool:
        if self.simulated or not GPIO.available:
            return self._sim_state

        v = GPIO.input(self.pin)
        return v if self.active_high else (not v)


    def on(self) -> None:
        if self.simulated:
            self._sim_state = True

    def off(self) -> None:
        if self.simulated:
            self._sim_state = False

    def toggle(self) -> None:
        if self.simulated:
            self._sim_state = not self._sim_state

    def press(self) -> None:
        self.on()

    def release(self) -> None:
        self.off()

    def cleanup(self) -> None:
        pass