from __future__ import annotations

class _GPIO:
    """@brief Thin wrapper around RPi.GPIO so the project can run on PC."""

    def __init__(self) -> None:
        self._gpio = None
        try:
            import RPi.GPIO as GPIO
            self._gpio = GPIO
            self._gpio.setmode(GPIO.BCM)
            self._gpio.setwarnings(False)
        except Exception:
            self._gpio = None

    @property
    def available(self) -> bool:
        return self._gpio is not None

    def setup_out(self, pin: int) -> None:
        if not self.available:
            return
        self._gpio.setup(pin, self._gpio.OUT)

    def setup_in(self, pin: int, pull: str = "down") -> None:
        """
        @brief Configure a pin as INPUT with optional pull-up/pull-down.
        @param pin BCM pin number
        @param pull "down" (default) or "up"
        """
        if not self.available:
            return

        pull_l = (pull or "down").lower()
        if pull_l == "up":
            pud = self._gpio.PUD_UP
        elif pull_l == "down":
            pud = self._gpio.PUD_DOWN
        else:
            pud = self._gpio.PUD_OFF

        self._gpio.setup(pin, self._gpio.IN, pull_up_down=pud)

    def output(self, pin: int, value: bool) -> None:
        if not self.available:
            return
        self._gpio.output(pin, self._gpio.HIGH if value else self._gpio.LOW)

    def input(self, pin: int) -> bool:
        """
        @brief Read a digital input pin.
        @return True if HIGH else False
        """
        if not self.available:
            return False
        return self._gpio.input(pin) == self._gpio.HIGH

    def cleanup(self) -> None:
        if not self.available:
            return
        self._gpio.cleanup()

GPIO = _GPIO()
