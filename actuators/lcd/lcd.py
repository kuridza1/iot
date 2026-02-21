from dataclasses import dataclass
from typing import Optional


@dataclass
class Lcd:
    """
    @brief LCD abstraction (simulated or real I2C 16x2 via PCF8574).

    - simulated=True  -> stores text only
    - simulated=False -> drives real LCD (address 0x27 by default)
    """
    simulated: bool = True
    address: int = 0x27
    cols: int = 16
    rows: int = 2

    _lcd: Optional[object] = None

    def __post_init__(self) -> None:
        self._text = ""

        if not self.simulated:
            try:
                from .PCF8574 import PCF8574_GPIO
                from .Adafruit_LCD1602 import Adafruit_CharLCD

                mcp = PCF8574_GPIO(self.address)

                self._lcd = Adafruit_CharLCD(
                    pin_rs=0,
                    pin_e=2,
                    pins_db=[4, 5, 6, 7],
                    GPIO=mcp
                )
                mcp.output(3, 1)
                
                self._lcd.begin(self.cols, self.rows)
                self._lcd.clear()

            except Exception:
                # Hardware unavailable → fallback to simulation
                self._lcd = None
                self.simulated = True

    def show(self, text: str) -> None:
        """
        Show text on LCD.
        If text contains newline → uses two lines.
        Otherwise auto-splits into rows.
        """
        self._text = str(text)

        if self.simulated or self._lcd is None:
            return

        lines = self._format_lines(self._text)

        self._lcd.clear()
        self._lcd.setCursor(0, 0)
        self._lcd.message(lines[0] + "\n")
        self._lcd.message(lines[1])

    def clear(self) -> None:
        self._text = ""

        if self.simulated or self._lcd is None:
            return

        self._lcd.clear()

    def last_text(self) -> str:
        return self._text

    def cleanup(self) -> None:
        if not self.simulated and self._lcd is not None:
            self._lcd.clear()

    def _format_lines(self, text: str):
        """Split text into exactly two LCD lines."""
        if "\n" in text:
            parts = text.split("\n", 1)
            line1 = parts[0][:self.cols]
            line2 = parts[1][:self.cols]
        else:
            padded = text.ljust(self.cols * self.rows)
            line1 = padded[:self.cols]
            line2 = padded[self.cols:self.cols * 2]

        return line1, line2
