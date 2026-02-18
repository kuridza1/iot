import random
import time
from typing import Callable, Optional

SPEED_OF_SOUND_CM_S = 34300.0

def _measure_distance_cm(GPIO, trig_pin: int, echo_pin: int, timeout_s: float = 0.02) -> Optional[float]:
    GPIO.output(trig_pin, False)
    time.sleep(0.0002)

    GPIO.output(trig_pin, True)
    time.sleep(0.00001)
    GPIO.output(trig_pin, False)

    start = time.time()
    while GPIO.input(echo_pin) == 0:
        if time.time() - start > timeout_s:
            return None
    pulse_start = time.time()

    while GPIO.input(echo_pin) == 1:
        if time.time() - pulse_start > timeout_s:
            return None
    pulse_end = time.time()

    pulse_duration = pulse_end - pulse_start
    return (pulse_duration * SPEED_OF_SOUND_CM_S) / 2.0


def run_ultrasonic_loop(
    delay: float,
    callback: Callable[[Optional[float]], None],
    stop_event,
    simulated: bool = True,
    trig_pin: int = 5,
    echo_pin: int = 6,
    max_cm: float = 200.0,
    timeout_s: float = 0.02,
) -> None:
    """
    Simulated OR real ultrasonic (HC-SR04).
    callback(distance_cm or None)
    """

    if simulated:

        THRESH = 50.0

   
        near_prob = 0.7      
        near_hold = 6.0        
        far_hold = 3.0         

        mode = "far"
        mode_until = time.time() + far_hold
        distance = 120.0

        while not stop_event.is_set():
            now = time.time()

            # promena režima
            if now >= mode_until:
                if mode == "far":
                    # povremeno neko "prilazi" (enter scenario)
                    if random.random() < near_prob:
                        mode = "near"
                        mode_until = now + near_hold
                        # skoči u near zonu
                        distance = random.uniform(10.0, THRESH - 5.0)
                    else:
                        mode = "far"
                        mode_until = now + far_hold
                        distance = random.uniform(THRESH + 20.0, 140.0)
                else:
                    # iz near se vraćamo u far (exit scenario)
                    mode = "far"
                    mode_until = now + far_hold
                    distance = random.uniform(THRESH + 20.0, 140.0)

            # update distance (mali random-walk oko ciljnog opsega)
            if mode == "near":
                distance += random.uniform(-3.0, 3.0)
                distance = min(THRESH - 2.0, max(5.0, distance))
            else:
                distance += random.uniform(-8.0, 8.0)
                distance = min(max_cm, max(THRESH + 5.0, distance))

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

    try:
        while not stop_event.is_set():
            d = _measure_distance_cm(GPIO, trig_pin, echo_pin, timeout_s=timeout_s)
            if d is not None and d > max_cm:
                d = None
            callback(None if d is None else round(d, 1))
            time.sleep(delay)
    finally:
        try:
            GPIO.cleanup((trig_pin, echo_pin))
        except Exception:
            pass
