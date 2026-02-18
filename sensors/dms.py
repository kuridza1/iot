from __future__ import annotations
import random
import time
from typing import Callable, List

KEYMAP = [
    ["1", "2", "3", "A"],
    ["4", "5", "6", "B"],
    ["7", "8", "9", "C"],
    ["*", "0", "#", "D"],
]


def run_membrane_loop(
    rows: List[int],
    cols: List[int],
    delay: float,
    callback: Callable[[str], None],
    stop_event,
    simulated: bool = True,
) -> None:
    """
    Simulated OR real 4x4 membrane keypad.
    callback(pin4) where pin4 is 4-digit string.

    - rows: BCM pins for row outputs (len=4)
    - cols: BCM pins for col inputs (len=4)
    """

    if simulated:
        while not stop_event.is_set():
            if random.random() < 0.1:
                callback("6236")
            else:
                pin = "".join(str(random.randint(0, 9)) for _ in range(4))
                callback(pin)
            time.sleep(float(delay) + random.uniform(1.0, 2.0))
        return

    try:
        import RPi.GPIO as GPIO
    except Exception as e:
        raise RuntimeError("RPi.GPIO nije dostupan. Vrati na simulated=True.") from e

    if len(rows) != 4 or len(cols) != 4:
        raise ValueError("rows i cols moraju imati po 4 pina (4x4 keypad).")

    GPIO.setmode(GPIO.BCM)

    for r in rows:
        GPIO.setup(int(r), GPIO.OUT)
        GPIO.output(int(r), GPIO.LOW)

    for c in cols:
        GPIO.setup(int(c), GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    pin_buffer = ""

    try:
        while not stop_event.is_set():
            for i, r in enumerate(rows):
                GPIO.output(int(r), GPIO.HIGH)

                for j, c in enumerate(cols):
                    if GPIO.input(int(c)) == GPIO.HIGH:
                        key = KEYMAP[i][j]

                        if key.isdigit():
                            pin_buffer += key
                            if len(pin_buffer) == 4:
                                callback(pin_buffer)
                                pin_buffer = ""

                        time.sleep(0.3) 

                GPIO.output(int(r), GPIO.LOW)

            time.sleep(float(delay))
    finally:
        try:
            GPIO.cleanup([*rows, *cols])
        except Exception:
            pass
