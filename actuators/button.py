from dataclasses import dataclass
from helper.helper import GPIO


@dataclass
class Button:
    """
    @brief Button input (digital)

    - simulated=True  -> stanje se kontroliše softverski (on/off/toggle)
    - simulated=False -> čita stvarni GPIO pin
    """
    simulated: bool
    pin: int
    active_high: bool = True
    pull: str = "down"   # "up" ili "down"

    def __post_init__(self) -> None:
        self._sim_state = False  # stanje za simulaciju

        if not self.simulated:
            GPIO.setup_in(self.pin, pull=self.pull)

    # -------------------------
    # READ
    # -------------------------
    def isOn(self) -> bool:
        if self.simulated or not GPIO.available:
            return self._sim_state

        v = GPIO.input(self.pin)
        return v if self.active_high else (not v)

    # -------------------------
    # SIMULATION CONTROL
    # -------------------------
    def on(self) -> None:
        """Simulate button pressed (ON)"""
        if self.simulated:
            self._sim_state = True

    def off(self) -> None:
        """Simulate button released (OFF)"""
        if self.simulated:
            self._sim_state = False

    def toggle(self) -> None:
        """Toggle simulated state"""
        if self.simulated:
            self._sim_state = not self._sim_state

    def press(self) -> None:
        """Alias for on()"""
        self.on()

    def release(self) -> None:
        """Alias for off()"""
        self.off()

    # -------------------------
    # CLEANUP
    # -------------------------
    def cleanup(self) -> None:
        pass