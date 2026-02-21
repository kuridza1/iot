from dataclasses import dataclass
from helper.helper import GPIO

@dataclass
class Button:
    """
    @brief Button input (digital)
    """
    simulated: bool
    pin: int
    active_high: bool = True
    pull: str = "down"   # "up" ili "down"

    def __post_init__(self) -> None:
        if not self.simulated:
            GPIO.setup_in(self.pin, pull=self.pull)

    def isOn(self) -> bool:
        if self.simulated or not GPIO.available:
            return False
        v = GPIO.input(self.pin)
        return v if self.active_high else (not v)

    def cleanup(self) -> None:
        pass
