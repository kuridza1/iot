# pi1/main.py
import threading
import time
import statistics
from collections import deque
from typing import Dict, Any, Optional

from actuators.button import Button
from actuators.buzzer import Buzzer
from actuators.led import Led

from helper.helper import GPIO
from helper.settings import load_settings
from mqtt.mqtt_publisher import MqttBatchPublisher

from security.alarm_controller import AlarmController
from security.config import load_alarm_pin, load_alarm_params
from helper.emit import make_emitter

from pi1.loops import start_ds1_loop, start_pir_loop, start_dus_loop, start_dms_loop


def ts_str() -> str:
    return time.strftime("%H:%M:%S", time.localtime())


def print_menu() -> None:
    print("\n==== PI1 SMART DOOR ====")
    print("1) Status")
    print("2) Toggle Door Light (DL)")
    print("3) Toggle Buzzer (DB)")
    print("4) Beep (DB)")
    print("5) Toggle Door Button (DS1)")
    print("6) Enter PIN (CMD)")
    print("0) Exit")


def run_cli(
    stop_event: threading.Event,
    alarm: AlarmController,
    led: Led,
    buzzer: Buzzer,
    button: Button,
    led_cfg: Dict[str, Any],
    buz_cfg: Dict[str, Any],
    btn_cfg: Dict[str, Any],
    safe_print,
    emit,
    set_suppress,
) -> None:
    print_menu()

    while not stop_event.is_set():
        raw = input("> ").strip()

        if raw == "1":
            safe_print(f"Alarm state: {alarm.state.value}")
            safe_print(f"Buzzer (DB): {'ON' if buzzer.isOn() else 'OFF'}")
            emit("security", "ALARM_STATE", alarm.state.value, None, True)
            emit("actuator", "DB", buzzer.isOn(), None, bool(buz_cfg.get("simulated", True)))
        elif raw == "2":
            if led.isOn():
                led.off()
                emit("actuator", "DL", False, None, bool(led_cfg.get("simulated", True)))
            else:
                led.on()
                emit("actuator", "DL", True, None, bool(led_cfg.get("simulated", True)))

        elif raw == "3":
            if buzzer.isOn():
                buzzer.off()
                emit("actuator", "DB", False, None, bool(buz_cfg.get("simulated", True)))
            else:
                buzzer.on()
                emit("actuator", "DB", True, None, bool(buz_cfg.get("simulated", True)))

        elif raw == "4":
            buzzer.beep(1)
            emit("actuator", "DB_BEEP", 1.0, "sec", bool(buz_cfg.get("simulated", True)))

        elif raw == "5":
            # Simulation: toggle DS1 raw level via Button
            if button.isOn():
                button.off()
                emit("actuator", "DS1_SIM_RAW", False, None, bool(btn_cfg.get("simulated", True)))
            else:
                button.on()
                emit("actuator", "DS1_SIM_RAW", True, None, bool(btn_cfg.get("simulated", True)))

        elif raw == "6":
            set_suppress(True)
            try:
                entered = input("PIN (4 digits): ").strip()
            finally:
                set_suppress(False)
            alarm.submit_pin(entered, source="CMD")

        elif raw == "0":
            stop_event.set()


def main() -> None:
    cfg = load_settings("pi1/settings.json")
    stop_event = threading.Event()

    device_cfg = cfg.get("device", {})
    pi_id = str(device_cfg.get("pi_id", "PI1"))
    device_name = str(device_cfg.get("device_name", "Device"))

    publisher = MqttBatchPublisher(cfg.get("mqtt", {}))
    publisher.start()

    emit, safe_print, set_suppress = make_emitter(
        publisher, device=pi_id, device_name=device_name, ts_str=ts_str
    )

    led_cfg = cfg.get("DL", {"simulated": True})
    buz_cfg = cfg.get("DB", {"simulated": True})
    btn_cfg = cfg.get("DS1", {"simulated": True})

    led = Led(**led_cfg)
    buzzer = Buzzer(**buz_cfg)
    button = Button(**btn_cfg)

    pin = load_alarm_pin(cfg)
    exit_delay, entry_delay, door_held = load_alarm_params(cfg)

    # Explicit close: only makes sense when DS1 is simulated (you can still call it safely)
    def close_doors():
        # Force DS1 "closed" in simulation
        if bool(btn_cfg.get("simulated", True)):
            if button.isOn():
                button.off()
            # Emit semantic "closed" event for dashboards
            emit("security", "DOOR_FORCE_CLOSED", "DS1", None, True)

    alarm = AlarmController(
        buzzer=buzzer,
        emit=emit,
        pin=pin,
        exit_delay_sec=exit_delay,
        entry_delay_sec=entry_delay,
        close_doors_cb=close_doors,  # <-- NEW
    )

    # ---------- DUS window + people count ----------
    state_lock = threading.Lock()
    people_inside = 0
    last_count_ts = 0.0
    dus_hist = deque()

    THRESH_CM = 50.0
    DUS_WINDOW_SEC = 3.0
    COOLDOWN_SEC = 2.5

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

    AUTO_ON_SEC = 10.0
    light_timer: Optional[threading.Timer] = None
    timer_lock = threading.Lock()

    def _dl_off():
        if led.isOn():
            led.off()
            emit("actuator", "DL", False, None, bool(led_cfg.get("simulated", True)))

    def on_pir(motion: bool) -> None:
        nonlocal light_timer, people_inside, last_count_ts
        emit("sensor", "DPIR1", motion, None, True)
        if not motion:
            return

        if not led.isOn():
            led.on()
            emit("actuator", "DL", True, None, bool(led_cfg.get("simulated", True)))

        with timer_lock:
            if light_timer:
                light_timer.cancel()
            light_timer = threading.Timer(AUTO_ON_SEC, _dl_off)
            light_timer.daemon = True
            light_timer.start()

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

    # ---------- DMS mapping + buffer ----------
    dms_map = cfg.get("DMS_MAP", {})
    pin_buf_lock = threading.Lock()
    pin_buf: list[str] = []

    def _pin_append(d: str) -> Optional[str]:
        with pin_buf_lock:
            pin_buf.append(d)
            if len(pin_buf) < 4:
                return None
            s = "".join(pin_buf[:4])
            pin_buf.clear()
            return s

    def on_dms_pin(pin_code: int) -> None:
        digit = None
        if isinstance(dms_map, dict) and dms_map:
            digit = dms_map.get(str(pin_code), dms_map.get(pin_code))

        if digit is None:
            emit("sensor", "DMS_PIN", pin_code, None, True)
            return

        d = str(digit)
        emit("sensor", "DMS_KEY", d, None, True)

        if not d.isdigit() or len(d) != 1:
            return

        candidate = _pin_append(d)
        if candidate is None:
            return

        alarm.submit_pin(candidate, source="DMS")

    # ---------- loops ----------
    threads = []
    threads.append(start_ds1_loop(button, alarm, emit, btn_cfg, 0.02, stop_event, door_held))
    threads.append(start_pir_loop(cfg.get("DPIR1", {"delay_sec": 1.5, "simulated": True}), on_pir, stop_event))
    threads.append(start_dus_loop(cfg.get("DUS1", {"delay_sec": 2.0, "simulated": True}), on_dus1, stop_event))
    threads.append(start_dms_loop(cfg.get("DMS", {}), on_dms_pin, stop_event))

    emit("security", "ALARM_STATE", alarm.state.value, None, True)

    try:
        run_cli(
            stop_event=stop_event,
            alarm=alarm,
            led=led,
            buzzer=buzzer,
            button=button,
            led_cfg=led_cfg,
            buz_cfg=buz_cfg,
            btn_cfg=btn_cfg,
            safe_print=safe_print,
            emit=emit,
            set_suppress=set_suppress,
        )
    finally:
        stop_event.set()
        publisher.stop()
        GPIO.cleanup()


if __name__ == "__main__":
    main()