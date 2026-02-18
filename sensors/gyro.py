import random
import time
import math
from typing import Callable


def run_gsg_loop(
    delay: float,
    threshold: float,
    callback: Callable[[bool], None],
    stop_event,
    simulated: bool = True,
) -> None:
    """
    Simulated OR real MPU6050 shake detector (GSG).

    callback(True) kada je detektovan pokret.
    """

    # ---------- SIMULATED ----------
    if simulated:
        baseline = 1.0 + random.uniform(-0.02, 0.02)

        while not stop_event.is_set():
            # mali šum oko baseline (~1g)
            magnitude = baseline + random.uniform(-0.03, 0.03)

            # povremeni "shake"
            if random.random() < 0.08:
                magnitude += random.choice([-1, 1]) * random.uniform(threshold + 0.05, threshold + 0.8)

            if abs(magnitude - baseline) > threshold:
                callback(True)

            time.sleep(delay)

        return

    # ---------- REAL SENSOR ----------
    try:
        import helper.MPU6050 as MPU6050
    except Exception as e:
        raise RuntimeError("MPU6050 modul nije dostupan. Vrati na simulated=True.") from e

    mpu = MPU6050.MPU6050()
    mpu.dmp_initialize()

    baseline = None

    while not stop_event.is_set():
        accel = mpu.get_acceleration()

        x = accel[0] / 16384.0
        y = accel[1] / 16384.0
        z = accel[2] / 16384.0

        magnitude = math.sqrt(x*x + y*y + z*z)

        if baseline is None:
            baseline = magnitude

        if abs(magnitude - baseline) > threshold:
            callback(True)

        time.sleep(delay)
