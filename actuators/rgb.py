from dataclasses import dataclass
from helper import GPIO


@dataclass
class BRGB:
    """
    @brief Bedroom RGB lamp (digital ON/OFF per channel).

    Each color channel is one GPIO pin:
      - True  -> ON
      - False -> OFF
    """
    simulated: bool
    pin_r: int
    pin_g: int
    pin_b: int
    active_high: bool = True

    def __post_init__(self) -> None:
        self._r = False
        self._g = False
        self._b = False

        if not self.simulated:
            GPIO.setup_out(self.pin_r)
            GPIO.setup_out(self.pin_g)
            GPIO.setup_out(self.pin_b)

        self.off()
        
    def _write(self, pin: int, state: bool) -> None:
        if self.simulated or not GPIO.available:
            return

        value = state if self.active_high else (not state)
        GPIO.output(pin, value)

    def set(self, r: bool, g: bool, b: bool) -> None:
        self._r = bool(r)
        self._g = bool(g)
        self._b = bool(b)

        self._write(self.pin_r, self._r)
        self._write(self.pin_g, self._g)
        self._write(self.pin_b, self._b)

    def set_color(self, r: bool, g: bool, b: bool) -> None:
        self.set(r, g, b)

    def on(self) -> None:
        self.set(True, True, True)

    def off(self) -> None:
        self.set(False, False, False)

    def red(self) -> None:
        self.set(True, False, False)

    def green(self) -> None:
        self.set(False, True, False)

    def blue(self) -> None:
        self.set(False, False, True)

    def yellow(self) -> None:
        self.set(True, True, False)

    def cyan(self) -> None:
        self.set(False, True, True)

    def magenta(self) -> None:
        self.set(True, False, True)

    def white(self) -> None:
        self.set(True, True, True)

    def isOn(self) -> bool:
        return self._r or self._g or self._b

    def get(self):
        return {
            "r": self._r,
            "g": self._g,
            "b": self._b,
        }

    def cleanup(self) -> None:
        self.off()
