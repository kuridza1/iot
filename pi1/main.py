import threading
import time
from typing import Dict, Any

from actuators.buzzer import Buzzer
from actuators.led import Led
from helper import GPIO
from sensors import run_button_loop, run_pir_loop, run_ultrasonic_loop
from settings import load_settings


def ts() -> str:
    return time.strftime("%H:%M:%S", time.localtime())


def event(label: str, payload: str) -> None:
    # Keep sensor output compact (threads will print anytime)
    print(f"\n[{ts()}] {label}: {payload}")


def print_menu() -> None:
    print("\n==== PI1 SMART DOOR (SIMPLE) ====")
    print("1) Status")
    print("2) Toggle Door Light (DL)")
    print("3) Toggle Buzzer (DB)")
    print("4) Beep (DB)  -> optional seconds")
    print("0) Exit")


def main() -> None:
    cfg: Dict[str, Any] = load_settings("settings.json")

    stop_event = threading.Event()
    threads: list[threading.Thread] = []

    # --- Actuators ---
    led_cfg = cfg.get("DL", {"simulated": True, "pin": 21, "active_high": True})
    buz_cfg = cfg.get("DB", {"simulated": True, "pin": 22, "active_high": True})

    led = Led(
        simulated=bool(led_cfg.get("simulated", True)),
        pin=int(led_cfg.get("pin", 21)),
        active_high=bool(led_cfg.get("active_high", True)),
    )
    buzzer = Buzzer(
        simulated=bool(buz_cfg.get("simulated", True)),
        pin=int(buz_cfg.get("pin", 22)),
        active_high=bool(buz_cfg.get("active_high", True)),
    )

    # --- Sensor loops (threads) ---
    ds_cfg = cfg.get("DS1", {"delay_sec": 1.5})
    dpir_cfg = cfg.get("DPIR1", {"delay_sec": 1.5})
    dus_cfg = cfg.get("DUS1", {"delay_sec": 2.0})

    t = threading.Thread(
        target=run_button_loop,
        args=(
            float(ds_cfg.get("delay_sec", 1.5)),
            lambda pressed: event("DS1(Button)", f"pressed={pressed}"),
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    t = threading.Thread(
        target=run_pir_loop,
        args=(
            float(dpir_cfg.get("delay_sec", 1.5)),
            lambda motion: event("DPIR1(PIR)", f"motion={motion}"),
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
            lambda d: event("DUS1(Ultrasonic)", f"distance_cm={d}"),
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # --- CLI (simple menu) ---
    print_menu()

    try:
        while not stop_event.is_set():
            try:
                raw = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                raw = "0"

            if not raw:
                continue

            # allow: "4" or "4 1.5"
            parts = raw.split()
            choice = parts[0]

            if choice == "1":
                print("\n--- STATUS ---")
                print(f"DL (Door Light): {'ON' if led.isOn() else 'OFF'}")
                print(f"DB (Buzzer):     {'ON' if buzzer.isOn() else 'OFF'}")

            elif choice == "2":
                if led.isOn():
                    led.off()
                    print("[DL] OFF")
                else:
                    led.on()
                    print("[DL] ON")

            elif choice == "3":
                if buzzer.isOn():
                    buzzer.off()
                    print("[DB] OFF")
                else:
                    buzzer.on()
                    print("[DB] ON")

            elif choice == "4":
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
                    print(f"[DB] BEEP {seconds:.2f}s")

            elif choice == "0":
                print("Exiting...")
                stop_event.set()

            else:
                print("Invalid option.")
                # don’t spam menu constantly, but helpful after mistakes:
                print_menu()

            time.sleep(0.1)

    finally:
        stop_event.set()
        time.sleep(0.1)

        # Cleanup
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
