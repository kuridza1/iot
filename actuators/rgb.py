from dataclasses import dataclass
from helper import GPIO


def clamp(v, lo, hi):
    return max(lo, min(hi, int(v)))


@dataclass
class BRGB:
    """
    @brief Bedroom RGB lamp with brightness control
    Brightness: 0–100 (%)
    RGB: 0–255
    """
    simulated: bool
    pin_r: int
    pin_g: int
    pin_b: int

    def __post_init__(self) -> None:
        self._brightness = 0
        self._r = 0
        self._g = 0
        self._b = 0

        if not self.simulated:
            GPIO.setup_out(self.pin_r)
            GPIO.setup_out(self.pin_g)
            GPIO.setup_out(self.pin_b)

    # -------------------------
    # Core control
    # -------------------------

    def set(self, brightness: int, r: int, g: int, b: int) -> None:
        self._brightness = clamp(brightness, 0, 100)
        self._r = clamp(r, 0, 255)
        self._g = clamp(g, 0, 255)
        self._b = clamp(b, 0, 255)

        if self.simulated or not GPIO.available:
            return

        # Scale RGB by brightness
        scale = self._brightness / 100.0

        r_val = int(self._r * scale)
        g_val = int(self._g * scale)
        b_val = int(self._b * scale)

        # Digital fallback (ON if > 0)
        GPIO.output(self.pin_r, r_val > 0)
        GPIO.output(self.pin_g, g_val > 0)
        GPIO.output(self.pin_b, b_val > 0)

    # -------------------------
    # Convenience methods
    # -------------------------

    def on(self) -> None:
        if self._brightness == 0:
            self._brightness = 100
        self.set(self._brightness, self._r, self._g, self._b)

    def off(self) -> None:
        self.set(0, 0, 0, 0)

    def set_brightness(self, brightness: int) -> None:
        self.set(brightness, self._r, self._g, self._b)

    def set_color(self, r: int, g: int, b: int) -> None:
        self.set(self._brightness, r, g, b)

    # -------------------------
    # State getters
    # -------------------------

    def isOn(self) -> bool:
        return self._brightness > 0 and (self._r or self._g or self._b)

    def get(self):
        return {
            "brightness": self._brightness,
            "r": self._r,
            "g": self._g,
            "b": self._b,
        }

    def cleanup(self) -> None:
        pass
