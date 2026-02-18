import random
import time
from typing import Callable, Optional


def run_ultrasonic_loop(
    delay: float,
    callback: Callable[[float], None],
    stop_event,
    simulated: bool = True,
    trig_pin: int = 5,
    echo_pin: int = 6,
) -> None:
    """
    Simulated OR real ultrasonic distance sensor (HC-SR04).

    - trig_pin: BCM pin za TRIG
    - echo_pin: BCM pin za ECHO
    """

    # ---------- SIMULATED ----------
    if simulated:
        distance = 120.0
        while not stop_event.is_set():
            if random.random() < 0.1:
                distance = random.uniform(10.0, 40.0)
            else:
                distance += random.uniform(-8.0, 8.0)
                distance = min(200.0, max(5.0, distance))

            callback(round(distance, 1))
            time.sleep(delay)
        return

    # ---------- REAL SENSOR ----------
    try:
        import RPi.GPIO as GPIO
    except Exception as e:
        raise RuntimeError("RPi.GPIO nije dostupna. Vrati na simulated=True.") from e

    GPIO.setmode(GPIO.BCM)

    GPIO.setup(trig_pin, GPIO.OUT)
    GPIO.setup(echo_pin, GPIO.IN)

    GPIO.output(trig_pin, False)
    time.sleep(0.2)  # stabilizacija senzora

    try:
        while not stop_event.is_set():

            # TRIG pulse (10 µs)
            GPIO.output(trig_pin, True)
            time.sleep(0.00001)
            GPIO.output(trig_pin, False)

            # čekaj početak ECHO
            start = time.time()
            timeout = start + 0.04

            while GPIO.input(echo_pin) == 0:
                start = time.time()
                if start > timeout:
                    start = None
                    break

            if start is None:
                continue

            # čekaj kraj ECHO
            stop = time.time()
            while GPIO.input(echo_pin) == 1:
                stop = time.time()
                if stop > timeout:
                    stop = None
                    break

            if stop is None:
                continue

            elapsed = stop - start

            # brzina zvuka ≈ 343 m/s
            distance_cm = (elapsed * 34300) / 2

            callback(round(distance_cm, 1))

            time.sleep(delay)

    finally:
        try:
            GPIO.cleanup((trig_pin, echo_pin))
        except Exception:
            pass
