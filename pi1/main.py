import threading
import time
from typing import Dict, Any

from actuators.buzzer import Buzzer
from actuators.led import Led
from helper import GPIO
from sensors import run_button_loop, run_pir_loop, run_ultrasonic_loop
from settings import load_settings

def ts() -> str:
    return time.strftime('%H:%M:%S', time.localtime())

def print_event(label: str, payload: str) -> None:
    print("=" * 28)
    print(f"[{ts()}] {label}")
    print(payload)

def main() -> None:
    cfg: Dict[str, Any] = load_settings("settings.json")

    stop_event = threading.Event()
    threads: list[threading.Thread] = []

    led_cfg = cfg.get("DL", {"simulated": True, "pin": 21, "active_high": True})
    buz_cfg = cfg.get("DB", {"simulated": True, "pin": 22, "active_high": True})

    actuators = {
        "DL": Led(simulated=bool(led_cfg.get("simulated", True)),
                  pin=int(led_cfg.get("pin", 21)),
                  active_high=bool(led_cfg.get("active_high", True))),
        "DB": Buzzer(simulated=bool(buz_cfg.get("simulated", True)),
                     pin=int(buz_cfg.get("pin", 22)),
                     active_high=bool(buz_cfg.get("active_high", True))),
    }

    ds_cfg = cfg.get("DS1", {"delay_sec": 1.5})
    dpir_cfg = cfg.get("DPIR1", {"delay_sec": 1.5})
    dus_cfg = cfg.get("DUS1", {"delay_sec": 2.0})

    t = threading.Thread(target=run_button_loop,
                         args=(float(ds_cfg.get("delay_sec", 1.5)),
                               lambda pressed: print_event("DS1 (Button)", f"pressed={pressed}"),
                               stop_event),
                         daemon=True)
    t.start(); threads.append(t)

    t = threading.Thread(target=run_pir_loop,
                         args=(float(dpir_cfg.get("delay_sec", 1.5)),
                               lambda motion: print_event("DPIR1 (PIR)", f"motion={motion}"),
                               stop_event),
                         daemon=True)
    t.start(); threads.append(t)

    t = threading.Thread(target=run_ultrasonic_loop,
                         args=(float(dus_cfg.get("delay_sec", 2.0)),
                               lambda d: print_event("DUS1 (Ultrasonic)", f"distance_cm={d}"),
                               stop_event),
                         daemon=True)
    t.start(); threads.append(t)

    # CLI
    help_text = (
        "\nCOMMANDS\n"
        "[1] led on|off\n"
        "[2] buzzer on|off\n"
        "[3] beep [seconds]\n"
        "[S] status\n"
        "[H] help\n"
        "[X] exit\n"
    )
    print(help_text)

    try:
        while not stop_event.is_set():
            try:
                cmd = input("pi1> ").strip()
            except (EOFError, KeyboardInterrupt):
                cmd = "exit"

            if not cmd:
                continue

            parts = cmd.split()
            c = parts[0].lower()

            if c == "help":
                print(help_text)
            elif c == "status":
                print("Actuators:", ", ".join(sorted(actuators.keys())))
            elif c == "led" and len(parts) >= 2:
                if parts[1].lower() == "on":
                    actuators["DL"].on()
                    print("[DL] Lights are on.")
                elif parts[1].lower() == "off":
                    actuators["DL"].off()
                    print("[DL] Lights are off.")
            elif c == "buzzer" and len(parts) >= 2:
                if parts[1].lower() == "on":
                    actuators["DB"].on()
                    print("[DB] Buzzer is on.")
                elif parts[1].lower() == "off":
                    actuators["DB"].off()
                    print("[DB] Buzzer is off.")
            elif c == "beep" and actuators["DB"].isOn():
                seconds = 1
                if len(parts) >= 2:
                    try:
                        seconds = float(parts[1])
                    except ValueError:
                        pass
                actuators["DB"].beep(seconds)
                print("BEEP!")
            elif c == "beep" and not actuators["DB"].isOn():
                print("You can't beep when buzzer is off.")
            elif c == "exit":
                stop_event.set()
            else:
                print("Unknown command. Type 'help'.")
    finally:
        stop_event.set()
        time.sleep(0.1)
        for a in actuators.values():
            try:
                a.cleanup()
            except Exception:
                pass
        try:
            GPIO.cleanup()
        except Exception:
            pass

if __name__ == "__main__":
    main()
