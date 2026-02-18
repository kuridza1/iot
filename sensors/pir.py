import random
import time
from typing import Callable, Optional

def run_pir_loop(
    delay: float,
    callback: Callable[[bool], None],
    stop_event,
    simulated: bool = True,
    pin: int = 17,
    pull: str = "down",        
    active_high: bool = True,    
) -> None:
    """
    Simulated PIR (random bursts) OR real PIR via RPi.GPIO.

    - pin: BCM pin broj (npr 17)
    - pull: "down" ili "up" 
    - active_high: True ako motion = HIGH
    """
    if simulated:
        motion = False
        burst_left = 0
        while not stop_event.is_set():
            if burst_left <= 0 and random.random() < 0.15:
                burst_left = random.randint(2, 6)
                motion = True
                callback(True)
            elif burst_left > 0:
                burst_left -= 1
                if burst_left == 0 and motion:
                    motion = False
                    callback(False)
            time.sleep(delay)
        return
    try:
        import RPi.GPIO as GPIO
    except Exception as e:
        raise RuntimeError("RPi.GPIO nije dostupna. Vrati na simulated=True.") from e

    GPIO.setmode(GPIO.BCM)

    if pull.lower() == "up":
        pud = GPIO.PUD_UP
    elif pull.lower() == "down":
        pud = GPIO.PUD_DOWN
    else:
        pud = GPIO.PUD_OFF

    GPIO.setup(int(pin), GPIO.IN, pull_up_down=pud)

    last_state: Optional[bool] = None

    try:
        while not stop_event.is_set():
            raw = GPIO.input(int(pin)) 
            state = bool(raw) if active_high else (not bool(raw))

            if last_state is None or state != last_state:
                callback(state)
                last_state = state

            time.sleep(delay)
    finally:
        try:
            GPIO.cleanup(int(pin))
        except Exception:
            pass
