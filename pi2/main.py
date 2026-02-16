# pi2/main.py
import threading
import time
import random
from typing import Dict, Any, Callable, Optional, Tuple

from mqtt.mqtt_publisher import MqttBatchPublisher
from telemetry import TelemetryEvent, now_ts
from helper import GPIO

from actuators.button import Button
from actuators.four_digit_timer import FourDigitTimer
from sensors.ultrasonic import run_ultrasonic_loop
from sensors.pir import run_pir_loop
from settings import load_settings
from sensors.gyro import run_gyro_loop
from sensors.timer import run_timer_loop


def ts_str() -> str:
    return time.strftime("%H:%M:%S", time.localtime())


def print_menu() -> None:
    print("\n==== PI2 KITCHEN + DOOR ====")
    print("1) Status")
    print("2) Toggle Door Sensor (DS2)")
    print("3) Toggle Kitchen Button (BTN)")
    print("4) Timer set <sec> (4SD)")
    print("5) Timer start/stop (4SD)")
    print("6) Timer reset (4SD)")
    print("0) Exit")


def main() -> None:
    cfg: Dict[str, Any] = load_settings("pi2/settings.json")

    device_cfg = cfg.get("device", {})
    pi_id = str(device_cfg.get("pi_id", "PI2"))
    device_name = str(device_cfg.get("device_name", "Device"))
    default_simulated = bool(device_cfg.get("default_simulated", True))

    mqtt_cfg = cfg.get("mqtt", {"enabled": False})
    publisher = MqttBatchPublisher(mqtt_cfg)
    publisher.start()

    stop_event = threading.Event()
    threads: list[threading.Thread] = []

    def emit(kind: str, code: str, value, unit: Optional[str], simulated: bool) -> None:
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
        print(f"\n[{ts_str()}] {kind.upper()} {code}: value={value} unit={unit} simulated={simulated}")


    ds2_cfg = cfg.get("DS2", {"simulated": default_simulated, "pin": 23, "active_high": True})
    btn_cfg = cfg.get("BTN", {"simulated": default_simulated, "pin": 24, "active_high": True})
    timer_cfg = cfg.get("4SD", {"simulated": default_simulated})

    ds2 = Button(
        simulated=bool(ds2_cfg.get("simulated", default_simulated)),
        pin=int(ds2_cfg.get("pin", 23)),
        active_high=bool(ds2_cfg.get("active_high", True)),
    )

    btn = Button(
        simulated=bool(btn_cfg.get("simulated", default_simulated)),
        pin=int(btn_cfg.get("pin", 24)),
        active_high=bool(btn_cfg.get("active_high", True)),
    )

    timer = FourDigitTimer(simulated=bool(timer_cfg.get("simulated", default_simulated)))


    dpir_cfg = cfg.get("DPIR2", {"delay_sec": 1.5, "simulated": default_simulated})
    dus_cfg = cfg.get("DUS2", {"delay_sec": 2.0, "simulated": default_simulated})
    gsg_cfg = cfg.get("GSG", {"delay_sec": 0.5, "simulated": default_simulated})

    t = threading.Thread(
        target=run_pir_loop,
        args=(
            float(dpir_cfg.get("delay_sec", 1.5)),
            lambda motion: emit("sensor", "DPIR2", bool(motion), None, bool(dpir_cfg.get("simulated", default_simulated))),
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    t = threading.Thread(
        target=run_ultrasonic_loop,
        args=(
            float(dus_cfg.get("delay_sec", 2.0)),
            lambda d: emit("sensor", "DUS2", float(d), "cm", bool(dus_cfg.get("simulated", default_simulated))),
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

# --- GSG thread (adds movement_cb) ---
    t = threading.Thread(
        target=run_gyro_loop,
        args=(
            float(gsg_cfg.get("delay_sec", 0.5)),
            # callback_xyz
            lambda xyz: (
                emit("sensor", "GSG_X", xyz[0], "deg/s", bool(gsg_cfg.get("simulated", default_simulated))),
                emit("sensor", "GSG_Y", xyz[1], "deg/s", bool(gsg_cfg.get("simulated", default_simulated))),
                emit("sensor", "GSG_Z", xyz[2], "deg/s", bool(gsg_cfg.get("simulated", default_simulated))),
            ),
            # movement_cb (NEW)
            lambda mag: emit("sensor", "GSG_MOVEMENT", mag, "mag", bool(gsg_cfg.get("simulated", default_simulated))),
            # stop_event
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)


    # --- 4SD timer thread (adds finished_cb) ---
    t = threading.Thread(
        target=run_timer_loop,
        args=(
            timer,
            lambda text, rem: emit("actuator", "4SD", text, None, bool(timer_cfg.get("simulated", default_simulated))),
            lambda: emit("actuator", "4SD_FINISHED", True, None, bool(timer_cfg.get("simulated", default_simulated))),
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)



    print_menu()

    try:
        while not stop_event.is_set():
            try:
                raw = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                raw = "0"

            if not raw:
                continue

            parts = raw.split()
            choice = parts[0]

            if choice == "1":
                running, left = timer.status()
                print("\n--- STATUS ---")
                print(f"DS2 (Door sensor):      {'ON' if ds2.isOn() else 'OFF'}")
                print(f"BTN (Kitchen button):   {'ON' if btn.isOn() else 'OFF'}")
                print(f"4SD (Timer):            {'RUN' if running else 'STOP'}  {timer.render()}  ({left}s)")

            elif choice == "2":
                if ds2.isOn():
                    ds2.off()
                    emit("actuator", "DS2", False, None, bool(ds2_cfg.get("simulated", default_simulated)))
                else:
                    ds2.on()
                    emit("actuator", "DS2", True, None, bool(ds2_cfg.get("simulated", default_simulated)))

            elif choice == "3":
                if btn.isOn():
                    btn.off()
                    emit("actuator", "BTN", False, None, bool(btn_cfg.get("simulated", default_simulated)))
                else:
                    btn.on()
                    emit("actuator", "BTN", True, None, bool(btn_cfg.get("simulated", default_simulated)))

            elif choice == "4":
                if len(parts) < 2:
                    print("Usage: 4 <seconds>")
                else:
                    try:
                        sec = int(float(parts[1]))
                        timer.set(sec)
                        emit("actuator", "4SD_SET", sec, "sec", bool(timer_cfg.get("simulated", default_simulated)))
                        print(f"[4SD] set to {sec}s ({timer.render()})")
                    except ValueError:
                        print("Invalid seconds.")

            elif choice == "5":
                running, _ = timer.status()
                if running:
                    timer.stop()
                    emit("actuator", "4SD_RUN", False, None, bool(timer_cfg.get("simulated", default_simulated)))
                    print("[4SD] STOP")
                else:
                    timer.start()
                    emit("actuator", "4SD_RUN", True, None, bool(timer_cfg.get("simulated", default_simulated)))
                    print("[4SD] START")

            elif choice == "6":
                timer.reset()
                emit("actuator", "4SD_RESET", True, None, bool(timer_cfg.get("simulated", default_simulated)))
                print("[4SD] RESET")

            elif choice == "0":
                stop_event.set()

            else:
                print("Invalid option.")
                print_menu()

            time.sleep(0.05)

    finally:
        stop_event.set()
        time.sleep(0.1)

        publisher.stop()

        try:
            ds2.cleanup()
        except Exception:
            pass
        try:
            btn.cleanup()
        except Exception:
            pass
        try:
            GPIO.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()
