import random
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from helper.helper import GPIO as GPIO_HELPER

DEFAULT_SIM_CODES = [
    "LEFT", "RIGHT", "UP", "DOWN",
    "2", "3", "1", "OK",
    "4", "5", "6", "7",
    "8", "9", "*", "0", "#"
]


@dataclass
class IRReceiver:
    """
    @brief HX1838 IR receiver (simulated or real).

    Important: helper.GPIO does not support inputs, so for real mode we use
    RPi.GPIO directly (only when available). Simulation still works on PC.
    """
    simulated: bool

    pin: int = 17

    # Loop / simulation
    delay: float = 0.10
    burst_prob: float = 0.15
    sim_codes: Optional[list[str]] = None

    one_threshold_us: int = 1000  
    end_idle_count: int = 10000  
    max_bits: int = 34           

    code_map: Optional[Dict[str, str]] = None

    def __post_init__(self) -> None:
        if self.sim_codes is None:
            self.sim_codes = DEFAULT_SIM_CODES

        if self.code_map is None:
            buttons = [
                0x300ff22dd, 0x300ffc23d, 0x300ff629d, 0x300ffa857,
                0x300ff9867, 0x300ffb04f, 0x300ff6897, 0x300ff02fd,
                0x300ff30cf, 0x300ff18e7, 0x300ff7a85, 0x300ff10ef,
                0x300ff38c7, 0x300ff5aa5, 0x300ff42bd, 0x300ff4ab5,
                0x300ff52ad
            ]
            names = [
                "LEFT", "RIGHT", "UP", "DOWN",
                "2", "3", "1", "OK",
                "4", "5", "6", "7",
                "8", "9", "*", "0", "#"
            ]
            self.code_map = {hex(code): name for code, name in zip(buttons, names)}

        self._rpi = None 

        if not self.simulated:
            if not GPIO_HELPER.available:
                raise RuntimeError("RPi.GPIO not available (running on PC?). Use simulated=True.")

            import RPi.GPIO as RPI
            self._rpi = RPI
            self._rpi.setmode(self._rpi.BCM)
            self._rpi.setwarnings(False)

            self._rpi.setup(self.pin, self._rpi.IN, pull_up_down=self._rpi.PUD_UP)


    def run_loop(self, callback: Callable[[str], None], stop_event) -> None:
        if self.simulated:
            self._run_sim(callback, stop_event)
        else:
            self._run_real(callback, stop_event)



    def _run_sim(self, callback: Callable[[str], None], stop_event) -> None:
        while not stop_event.is_set():
            if random.random() < float(self.burst_prob):
                callback(random.choice(self.sim_codes))
            time.sleep(float(self.delay))


    def _read_pin(self) -> int:
        return int(self._rpi.input(self.pin))

    def _get_binary(self) -> int:
        num1s = 0
        binary = 1
        command = []
        previous = 0
        value = self._read_pin()

        while value:
            time.sleep(0.0001)
            value = self._read_pin()

        start = time.perf_counter_ns()

        while True:
            if previous != value:
                now = time.perf_counter_ns()
                pulse_us = int((now - start) / 1000)
                start = now
                command.append((previous, pulse_us))

            if value:
                num1s += 1
            else:
                num1s = 0

            if num1s > int(self.end_idle_count):
                break

            previous = value
            value = self._read_pin()

        for typ, tme_us in command:
            if typ == 1:
                if tme_us > int(self.one_threshold_us):
                    binary = binary * 10 + 1
                else:
                    binary *= 10

        s = str(binary)
        if len(s) > int(self.max_bits):
            binary = int(s[: int(self.max_bits)])

        return binary

    def _convert_hex(self, binary_value: int) -> str:
        tmp = int(str(binary_value), 2)
        return hex(tmp)

    def _run_real(self, callback: Callable[[str], None], stop_event) -> None:
        while not stop_event.is_set():
            try:
                code_hex = self._convert_hex(self._get_binary())
                name = self.code_map.get(code_hex)
                if name:
                    callback(name)
            except Exception:
                pass
            time.sleep(float(self.delay))

    def cleanup(self) -> None:
        pass


def run_ir_loop(
    delay: float,
    burst_prob: float,
    callback: Callable[[str], None],
    stop_event,
    simulated: bool = True,
    pin: int = 17,
    code_map: Optional[Dict[str, str]] = None,
) -> None:
    rx = IRReceiver(
        simulated=simulated,
        pin=pin,
        delay=delay,
        burst_prob=burst_prob,
        code_map=code_map,
    )
    rx.run_loop(callback, stop_event)
