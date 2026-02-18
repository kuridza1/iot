import threading
import time
import statistics
from collections import deque
from typing import Dict, Any, Optional

from actuators.button import Button
from actuators.buzzer import Buzzer
from actuators.led import Led

from mqtt.mqtt_publisher import MqttBatchPublisher
from sensors.ultrasonic import run_ultrasonic_loop
from sensors.pir import run_pir_loop
from sensors.dms import run_membrane_loop

from helper.settings import load_settings
from helper.telemetry import *
from helper.helper import GPIO


def ts_str() -> str:
    return time.strftime("%H:%M:%S", time.localtime())


def print_menu() -> None:
    print("\n==== PI1 SMART DOOR ====")
    print("1) Status")
    print("2) Toggle Door Light (DL)")
    print("3) Toggle Buzzer (DB)")
    print("4) Beep (DB)")
    print("5) Toggle Door Button (DS1)")
    print("0) Exit")


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    cfg: Dict[str, Any] = load_settings("pi1/settings.json")

    device_cfg = cfg.get("device", {})
    pi_id = str(device_cfg.get("pi_id", "PI1"))
    device_name = str(device_cfg.get("device_name", "Device"))
    default_simulated = bool(device_cfg.get("default_simulated", True))

    mqtt_cfg = cfg.get("mqtt", {"enabled": False})
    publisher = MqttBatchPublisher(mqtt_cfg)
    publisher.start()

    stop_event = threading.Event()
    threads: list[threading.Thread] = []

    # ============================================================
    # ACTUATORS
    # ============================================================

    led_cfg = cfg.get("DL", {"simulated": default_simulated, "pin": 21})
    buz_cfg = cfg.get("DB", {"simulated": default_simulated, "pin": 22})
    btn_cfg = cfg.get("DS1", {"simulated": default_simulated, "pin": 23})

    led = Led(**led_cfg)
    buzzer = Buzzer(**buz_cfg)
    button = Button(**btn_cfg)

    def emit(kind: str, code: str, value, unit: Optional[str], simulated: bool):
        ev = TelemetryEvent(
            device=pi_id,
            device_name=device_name,
            kind=kind,
            code=code,
            value=value,
            unit=unit,
            simulated=simulated,
            ts=now_ts(),
        )
        publisher.enqueue(ev)
        print(f"[{ts_str()}] {code}: {value}")

    # ============================================================
    # PEOPLE COUNT STATE
    # ============================================================

    THRESH_CM = 50.0
    DUS_WINDOW_SEC = 3.0
    COOLDOWN_SEC = 2.5

    dus_hist = deque()      # (timestamp, distance)
    people_inside = 0
    last_count_ts = 0.0

    state_lock = threading.Lock()

    # ============================================================
    # LIGHT AUTO-OFF (10s)
    # ============================================================

    AUTO_ON_SEC = 10.0
    light_timer: Optional[threading.Timer] = None
    timer_lock = threading.Lock()

    def _dl_off():
        if led.isOn():
            led.off()
            emit("actuator", "DL", False, None, led_cfg["simulated"])

    # ============================================================
    # DUS CALLBACK
    # ============================================================

    def on_dus1(d: Optional[float]) -> None:
        emit("sensor", "DUS1", d, "cm", True)

        now = time.time()
        cutoff = now - DUS_WINDOW_SEC

        with state_lock:
            if d is not None:
                dus_hist.append((now, float(d)))

            while dus_hist and dus_hist[0][0] < cutoff:
                dus_hist.popleft()

    def dus_zone() -> Optional[str]:
        with state_lock:
            ds = [d for _, d in dus_hist]

        if len(ds) < 2:
            return None

        m = statistics.median(ds)
        return "SMALL" if m < THRESH_CM else "BIG"

    # ============================================================
    # PIR CALLBACK
    # ============================================================

    def on_pir(motion: bool) -> None:
        nonlocal light_timer, people_inside, last_count_ts

        emit("sensor", "DPIR1", motion, None, True)

        if not motion:
            return

        # ---------- LIGHT ----------
        if not led.isOn():
            led.on()
            emit("actuator", "DL", True, None, led_cfg["simulated"])

        with timer_lock:
            if light_timer:
                light_timer.cancel()
            light_timer = threading.Timer(AUTO_ON_SEC, _dl_off)
            light_timer.daemon = True
            light_timer.start()

        # ---------- ANTI DOUBLE COUNT ----------
        now = time.time()
        with state_lock:
            if now - last_count_ts < COOLDOWN_SEC:
                return

        zone = dus_zone()
        if zone is None:
            emit("sensor", "DOOR_DIR", "UNKNOWN", None, True)
            return

        enter_exit = "ENTER" if zone == "SMALL" else "EXIT"

        with state_lock:
            if enter_exit == "ENTER":
                people_inside += 1
            else:
                people_inside = max(0, people_inside - 1)

            last_count_ts = now
            current = people_inside

        emit("sensor", "DOOR_DIR", enter_exit, None, True)
        emit("sensor", "PEOPLE_INSIDE", current, "count", True)

    # ============================================================
    # THREADS — PIR
    # ============================================================

    dpir_cfg = cfg.get("DPIR1", {"delay_sec": 1.5, "simulated": True})

    t = threading.Thread(
        target=run_pir_loop,
        args=(
            dpir_cfg["delay_sec"],
            on_pir,
            stop_event,
            dpir_cfg["simulated"],
            dpir_cfg.get("pin", 17),
            dpir_cfg.get("pull", "down"),
            dpir_cfg.get("active_high", True),
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # ============================================================
    # THREADS — DUS
    # ============================================================

    dus_cfg = cfg.get("DUS1", {"delay_sec": 2.0, "simulated": True})

    t = threading.Thread(
        target=run_ultrasonic_loop,
        args=(
            dus_cfg["delay_sec"],
            on_dus1,
            stop_event,
            dus_cfg["simulated"],
            dus_cfg.get("trig_pin", 5),
            dus_cfg.get("echo_pin", 6),
            
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # ============================================================
    # THREADS — DMS
    # ============================================================

    dms_cfg = cfg.get(
        "DMS",
        {"delay_sec": 0.05, "simulated": True, "rows": [6, 13, 19, 26], "cols": [12, 16, 20, 21]},
    )

    t = threading.Thread(
        target=run_membrane_loop,
        args=(
            dms_cfg["rows"],
            dms_cfg["cols"],
            dms_cfg["delay_sec"],
            lambda pin: emit("sensor", "DMS_PIN", pin, None, True),
            stop_event,
            dms_cfg["simulated"],
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # ============================================================
    # CLI
    # ============================================================

    print_menu()

    try:
        while not stop_event.is_set():
            raw = input("> ").strip()

            if raw == "1":
                print(f"People inside: {people_inside}")
                emit("sensor", "PEOPLE_INSIDE", int(people_inside), "persons", True)

            elif raw == "2":
                if led.isOn():
                    led.off()
                    emit("actuator", "DL", False, None,
                        bool(led_cfg.get("simulated", default_simulated)))
                else:
                    led.on()
                    emit("actuator", "DL", True, None,
                        bool(led_cfg.get("simulated", default_simulated)))

            elif raw == "3":
                if buzzer.isOn():
                    buzzer.off()
                    emit("actuator", "DB", False, None,
                        bool(buz_cfg.get("simulated", default_simulated)))
                else:
                    buzzer.on()
                    emit("actuator", "DB", True, None,
                        bool(buz_cfg.get("simulated", default_simulated)))

            elif raw == "4":
                buzzer.beep(1)
                emit("actuator", "DB_BEEP", 1.0, "sec",
                    bool(buz_cfg.get("simulated", default_simulated)))

            elif raw == "5":
                if button.isOn():
                    button.off()
                    emit("actuator", "DS1", False, None,
                        bool(btn_cfg.get("simulated", default_simulated)))
                else:
                    button.on()
                    emit("actuator", "DS1", True, None,
                        bool(btn_cfg.get("simulated", default_simulated)))

            elif raw == "0":
                stop_event.set()

    finally:
        stop_event.set()
        publisher.stop()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
