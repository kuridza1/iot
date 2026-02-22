import threading
import time
from typing import Any, Dict, Optional, Callable

from sensors.pir import run_pir_loop
from sensors.ultrasonic import run_ultrasonic_loop
from sensors.dms import run_membrane_loop

def start_ds1_loop(button, alarm, emit, btn_cfg: Dict[str, Any],
                   delay_sec: float, stop_event: threading.Event,
                   door_held_sec: float) -> threading.Thread:

    active_high = bool(btn_cfg.get("active_high", True))
    simulated = bool(btn_cfg.get("simulated", True))

    def to_door_open(raw_level: bool) -> bool:
        return raw_level if active_high else (not raw_level)

    def loop():
        last_raw = None

        while not stop_event.is_set():
            raw = bool(button.isOn())
            now = time.time()
            door_open = to_door_open(raw)

            if last_raw is None or raw != last_raw:
                last_raw = raw
                if door_open:
                    alarm.on_door_event("DS1", "DOOR_OPEN")

                alarm.handle_ds1_level(door_open, now)

            # held detection on "open"
            alarm.check_ds1_held(now, door_held_sec)

            time.sleep(delay_sec)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def start_pir_loop(cfg: Dict[str, Any], on_pir: Callable, stop_event: threading.Event) -> threading.Thread:
    t = threading.Thread(
        target=run_pir_loop,
        args=(
            cfg["delay_sec"],
            on_pir,
            stop_event,
            cfg["simulated"],
            cfg.get("pin", 17),
            cfg.get("pull", "down"),
            cfg.get("active_high", True),
        ),
        daemon=True,
    )
    t.start()
    return t


def start_dus_loop(cfg: Dict[str, Any], on_dus: Callable, stop_event: threading.Event) -> threading.Thread:
    t = threading.Thread(
        target=run_ultrasonic_loop,
        args=(
            cfg["delay_sec"],
            on_dus,
            stop_event,
            cfg["simulated"],
            cfg.get("trig_pin", 5),
            cfg.get("echo_pin", 6),
        ),
        daemon=True,
    )
    t.start()
    return t


def start_dms_loop(cfg: Dict[str, Any], on_dms_pin: Callable, stop_event: threading.Event) -> threading.Thread:
    t = threading.Thread(
        target=run_membrane_loop,
        args=(
            cfg["rows"],
            cfg["cols"],
            cfg["delay_sec"],
            on_dms_pin,
            stop_event,
            cfg["simulated"],
        ),
        daemon=True,
    )
    t.start()
    return t