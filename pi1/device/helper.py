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

    def output(self, pin: int, value: bool) -> None:
        if not self.available:
            return
        self._gpio.output(pin, self._gpio.HIGH if value else self._gpio.LOW)

    def cleanup(self) -> None:
        if not self.available:
            return
        self._gpio.cleanup()

GPIO = _GPIO()
