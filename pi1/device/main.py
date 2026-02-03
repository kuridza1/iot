import threading
import time
from typing import Dict, Any

from actuators.button import Button
from actuators.buzzer import Buzzer
from actuators.led import Led
from helper import GPIO
from sensors.ultrasonic import run_ultrasonic_loop
from sensors.pir import run_pir_loop
from settings import load_settings

from telemetry import TelemetryEvent, now_ts
from mqtt.mqtt_publisher import MqttBatchPublisher


def ts_str() -> str:
    return time.strftime("%H:%M:%S", time.localtime())


def print_menu() -> None:
    print("\n==== PI1 SMART DOOR ====")
    print("1) Status")
    print("2) Toggle Door Light (DL)")
    print("3) Toggle Buzzer (DB)")
    print("4) Beep (DB)  -> optional seconds")
    print("5) Toggle Door Button (DS1)")
    print("0) Exit")


def main() -> None:
    cfg: Dict[str, Any] = load_settings("settings.json") 

    device_cfg = cfg.get("device", {})
    pi_id = str(device_cfg.get("pi_id", "PI1"))
    device_name = str(device_cfg.get("device_name", "Device"))
    default_simulated = bool(device_cfg.get("default_simulated", True))

    mqtt_cfg = cfg.get("mqtt", {"enabled": False})
    publisher = MqttBatchPublisher(mqtt_cfg)
    publisher.start()

    stop_event = threading.Event()
    threads: list[threading.Thread] = []

    # --- Actuators ---
    led_cfg = cfg.get("DL", {"simulated": default_simulated, "pin": 21, "active_high": True})
    buz_cfg = cfg.get("DB", {"simulated": default_simulated, "pin": 22, "active_high": True})
    btn_cfg = cfg.get("DS1", {"simulated": default_simulated, "pin": 23, "active_high": True})
    led = Led(
        simulated=bool(led_cfg.get("simulated", default_simulated)),
        pin=int(led_cfg.get("pin", 21)),
        active_high=bool(led_cfg.get("active_high", True)),
    )

    buzzer = Buzzer(
        simulated=bool(buz_cfg.get("simulated", default_simulated)),
        pin=int(buz_cfg.get("pin", 22)),
        active_high=bool(buz_cfg.get("active_high", True)),
    )

    button = Button(
        simulated=bool(btn_cfg.get("simulated", default_simulated)),
        pin=int(btn_cfg.get("pin", 23)),
        active_high=bool(btn_cfg.get("active_high", True)),
    )

    # helper to publish + print
    def emit(kind: str, code: str, value, unit: str | None, simulated: bool) -> None:
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

    # --- Sensor loops (threads) ---
    dpir_cfg = cfg.get("DPIR1", {"delay_sec": 1.5, "simulated": default_simulated})
    dus_cfg = cfg.get("DUS1", {"delay_sec": 2.0, "simulated": default_simulated})

    t = threading.Thread(
        target=run_pir_loop,
        args=(
            float(dpir_cfg.get("delay_sec", 1.5)),
            lambda motion: emit("sensor", "DPIR1", bool(motion), None, bool(dpir_cfg.get("simulated", default_simulated))),
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
            lambda d: emit("sensor", "DUS1", float(d), "cm", bool(dus_cfg.get("simulated", default_simulated))),
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # --- CLI ---
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
                print("\n--- STATUS ---")
                print(f"DL (Door Light): {'ON' if led.isOn() else 'OFF'}")
                print(f"DB (Buzzer):     {'ON' if buzzer.isOn() else 'OFF'}")
                print(f"DS1 (Door Button):     {'ON' if button.isOn() else 'OFF'}")

            elif choice == "2":
                if led.isOn():
                    led.off()
                    emit("actuator", "DL", False, None, bool(led_cfg.get("simulated", default_simulated)))
                    print("[DL] OFF")
                else:
                    led.on()
                    emit("actuator", "DL", True, None, bool(led_cfg.get("simulated", default_simulated)))
                    print("[DL] ON")

            elif choice == "3":
                if button.isOn():
                    button.off()
                    emit("actuator", "DS1", False, None, bool(buz_cfg.get("simulated", default_simulated)))
                    print("[DS1] OFF")
                else:
                    button.on()
                    emit("actuator", "DS1", True, None, bool(buz_cfg.get("simulated", default_simulated)))
                    print("[DS1] ON")

            elif choice == "4":
                if buzzer.isOn():
                    buzzer.off()
                    emit("actuator", "DB", False, None, bool(buz_cfg.get("simulated", default_simulated)))
                    print("[DB] OFF")
                else:
                    buzzer.on()
                    emit("actuator", "DB", True, None, bool(buz_cfg.get("simulated", default_simulated)))
                    print("[DB] ON")
        
            elif choice == "5":
                seconds = 1.0
                if len(parts) >= 2:
                    try:
                        seconds = float(parts[1])
                    except ValueError:
                        seconds = 1.0

                if not buzzer.isOn():
                    print("[DB] Buzzer is OFF. Turn it ON first (option 3).")
                else:
                    buzzer.beep(seconds)
                    emit("actuator", "DB_BEEP", seconds, "sec", bool(buz_cfg.get("simulated", default_simulated)))
                    print(f"[DB_BEEP] {seconds:.2f}s")

            elif choice == "0":
                print("Exiting...")
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
            led.cleanup()
        except Exception:
            pass
        try:
            buzzer.cleanup()
        except Exception:
            pass
        try:
            GPIO.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()
