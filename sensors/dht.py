import random
import time
from dataclasses import dataclass
from typing import Callable, Optional

from helper.helper import GPIO as GPIO_HELPER


@dataclass
class DHT11:
    simulated: bool
    pin: int

    delay: float = 2.0

    temp_c_start: float = 22.0
    hum_pct_start: float = 45.0

    _rpi: Optional[object] = None

    _WAKEUP_S: float = 0.020      
    _TIMEOUT_S: float = 0.010      

    def __post_init__(self) -> None:
        if not self.simulated:
            if not GPIO_HELPER.available:
                raise RuntimeError("RPi.GPIO not available. Use simulated=True on PC.")

            import RPi.GPIO as RPI
            self._rpi = RPI
            self._rpi.setmode(self._rpi.BCM)
            self._rpi.setwarnings(False)
            
    def run_loop(self, callback: Callable[[float, float], None], stop_event) -> None:
        if self.simulated:
            self._run_sim(callback, stop_event)
        else:
            self._run_real(callback, stop_event)

    def _run_sim(self, callback: Callable[[float, float], None], stop_event) -> None:
        temp = float(self.temp_c_start)
        hum = float(self.hum_pct_start)

        while not stop_event.is_set():
            temp += random.uniform(-0.2, 0.2)
            hum += random.uniform(-0.8, 0.8)

            temp = max(10.0, min(35.0, temp))
            hum = max(15.0, min(85.0, hum))

            callback(round(temp, 1), round(hum, 1))
            time.sleep(float(self.delay))

    def _wait_while(self, level: int, timeout_s: float) -> bool:
        t0 = time.perf_counter()
        while int(self._rpi.input(self.pin)) == level:
            if (time.perf_counter() - t0) > timeout_s:
                return False
        return True

    def _read_dht11_once(self) -> Optional[tuple[float, float]]:

        RPI = self._rpi

        RPI.setup(self.pin, RPI.OUT)
        RPI.output(self.pin, RPI.LOW)
        time.sleep(self._WAKEUP_S)

        RPI.output(self.pin, RPI.HIGH)
        time.sleep(0.00004)  
        RPI.setup(self.pin, RPI.IN)

        if not self._wait_while(1, self._TIMEOUT_S):  
            return None
        if not self._wait_while(0, self._TIMEOUT_S): 
            return None
        if not self._wait_while(1, self._TIMEOUT_S):  
            return None

        data = [0, 0, 0, 0, 0]

        for bit_i in range(40):
            if not self._wait_while(0, self._TIMEOUT_S):  
                return None

            t_high_start = time.perf_counter()
            if not self._wait_while(1, self._TIMEOUT_S):  
                return None
            high_len = time.perf_counter() - t_high_start

            bit = 1 if high_len > 0.00005 else 0

            byte_i = bit_i // 8
            data[byte_i] = (data[byte_i] << 1) | bit

        RPI.setup(self.pin, RPI.OUT)
        RPI.output(self.pin, RPI.HIGH)

        hum_i, hum_d, temp_i, temp_d, chk = data
        checksum = (hum_i + hum_d + temp_i + temp_d) & 0xFF
        if chk != checksum:
            return None

        hum = float(hum_i) + float(hum_d) * 0.1
        temp = float(temp_i) + float(temp_d) * 0.1
        return (temp, hum)

    def _run_real(self, callback: Callable[[float, float], None], stop_event) -> None:
        while not stop_event.is_set():
            try:
                reading = self._read_dht11_once()
                if reading is not None:
                    temp, hum = reading
                    callback(round(temp, 1), round(hum, 1))
            except Exception:
                pass
            time.sleep(float(self.delay))

    def cleanup(self) -> None:
        pass


def run_dht_loop(
    delay: float,
    temp_c_start: float,
    hum_pct_start: float,
    callback: Callable[[float, float], None],
    stop_event,
    simulated: bool = True,
    pin: int = 4,
) -> None:
    dht = DHT11(
        simulated=simulated,
        pin=pin,
        delay=delay,
        temp_c_start=temp_c_start,
        hum_pct_start=hum_pct_start,
    )
    dht.run_loop(callback, stop_event)
