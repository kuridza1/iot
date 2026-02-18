import threading
import time
from typing import Dict, Any

from helper import GPIO
from settings import load_settings

from telemetry import TelemetryEvent, now_ts
from mqtt.mqtt_publisher import MqttBatchPublisher

from sensors.pir import run_pir_loop
from sensors.dht import run_dht_loop
from sensors.ir import run_ir_loop

from actuators.rgb import BRGB
from actuators.lcd import Lcd


def ts_str() -> str:
    return time.strftime("%H:%M:%S", time.localtime())


def print_menu() -> None:
    print("\n==== PI3 SMART ROOMS ====")
    print("1) Status")
    print("2) BRGB: ON")
    print("3) BRGB: OFF")
    print("4) BRGB: Set (brightness r g b)  brightness 0-100, rgb 0-255  e.g. 80 255 0 40")
    print("5) BRGB: Set brightness (0-100)  e.g. 30")
    print("6) LCD: Show text   (free text)")
    print("0) Exit")


def main() -> None:
    cfg: Dict[str, Any] = load_settings("pi3/settings.json")

    device_cfg = cfg.get("device", {})
    pi_id = str(device_cfg.get("pi_id", "PI3"))
    device_name = str(device_cfg.get("device_name", "Device"))
    default_simulated = bool(device_cfg.get("default_simulated", True))

    mqtt_cfg = cfg.get("mqtt", {"enabled": False})
    publisher = MqttBatchPublisher(mqtt_cfg)
    publisher.start()

    stop_event = threading.Event()
    threads: list[threading.Thread] = []

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

    # --- Actuators ---
    rgb_cfg = cfg.get("BRGB", {"simulated": default_simulated})
    lcd_cfg = cfg.get("LCD", {"simulated": default_simulated})

    brgb = BRGB(
        simulated=bool(rgb_cfg.get("simulated", default_simulated)),
        pin_r=int(rgb_cfg.get("pin_r", 17)),
        pin_g=int(rgb_cfg.get("pin_g", 27)),
        pin_b=int(rgb_cfg.get("pin_b", 22)),
    )

    lcd = Lcd(simulated=bool(lcd_cfg.get("simulated", default_simulated)))

    dpir_cfg = cfg.get("DPIR3", {"delay_sec": 1.5, "simulated": default_simulated, "pin": 17, "pull": "down", "active_high": True})

    dpir_sim = bool(dpir_cfg.get("simulated", default_simulated))
    dpir_pin = int(dpir_cfg.get("pin", 17))
    dpir_pull = str(dpir_cfg.get("pull", "down"))
    dpir_active_high = bool(dpir_cfg.get("active_high", True))

    t = threading.Thread(
        target=run_pir_loop,
        args=(
            float(dpir_cfg.get("delay_sec", 1.5)),
            lambda motion: emit("sensor", "DPIR3", bool(motion), None, dpir_sim),
            stop_event,
            dpir_sim,
            dpir_pin,
            dpir_pull,
            dpir_active_high,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)
    dht1_cfg = cfg.get("DHT1", {"delay_sec": 3.0, "simulated": default_simulated})
    dht2_cfg = cfg.get("DHT2", {"delay_sec": 3.0, "simulated": default_simulated})
    ir_cfg = cfg.get("IR", {"delay_sec": 0.25, "simulated": default_simulated})

    t = threading.Thread(
        target=run_pir_loop,
        args=(
            float(dpir_cfg.get("delay_sec", 1.5)),
            lambda motion: emit("sensor", "DPIR3", bool(motion), None, bool(dpir_cfg.get("simulated", default_simulated))),
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    t = threading.Thread(
        target=run_dht_loop,
        args=(
            float(dht1_cfg.get("delay_sec", 3.0)),
            float(dht1_cfg.get("temp_c_start", 22.0)),
            float(dht1_cfg.get("hum_pct_start", 45.0)),
            lambda temp_c, hum_pct: (
                emit("sensor", "DHT1_TEMP", float(temp_c), "C", bool(dht1_cfg.get("simulated", default_simulated))),
                emit("sensor", "DHT1_HUM", float(hum_pct), "%", bool(dht1_cfg.get("simulated", default_simulated))),
            ),
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # DHT2 loop
    t = threading.Thread(
        target=run_dht_loop,
        args=(
            float(dht2_cfg.get("delay_sec", 3.0)),
            float(dht2_cfg.get("temp_c_start", 21.0)),
            float(dht2_cfg.get("hum_pct_start", 48.0)),
            lambda temp_c, hum_pct: (
                emit("sensor", "DHT2_TEMP", float(temp_c), "C", bool(dht2_cfg.get("simulated", default_simulated))),
                emit("sensor", "DHT2_HUM", float(hum_pct), "%", bool(dht2_cfg.get("simulated", default_simulated))),
            ),
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # IR loop: emits IR code strings like "POWER", "R", "G", "B", "OFF", etc.
    t = threading.Thread(
        target=run_ir_loop,
        args=(
            float(ir_cfg.get("delay_sec", 0.25)),
            float(ir_cfg.get("burst_prob", 0.06)),
            lambda code: emit("sensor", "IR", str(code), None, bool(ir_cfg.get("simulated", default_simulated))),
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
                r, g, b = brgb.get()
                print(f"BRGB: {'ON' if brgb.isOn() else 'OFF'}  color=({r},{g},{b})")
                print(f"LCD:  last='{lcd.last_text()}'")

            elif choice == "2":
                brgb.on()
                emit("actuator", "BRGB", True, None, bool(rgb_cfg.get("simulated", default_simulated)))
                print("[BRGB] ON")

            elif choice == "3":
                brgb.off()
                emit("actuator", "BRGB", False, None, bool(rgb_cfg.get("simulated", default_simulated)))
                print("[BRGB] OFF")

            elif choice == "4":
                if len(parts) < 5:
                    print("Usage: 4 brightness r g b   (0-100, 0-255, 0-255, 0-255)")
                else:
                    try:
                        br = int(parts[1]); r = int(parts[2]); g = int(parts[3]); b = int(parts[4])
                        brgb.set(br, r, g, b)
                        emit("actuator", "BRGB_SET", brgb.get(), None, bool(rgb_cfg.get("simulated", default_simulated)))
                        print(f"[BRGB] SET br={br} rgb=({r},{g},{b})")
                    except ValueError:
                        print("Invalid numbers.")

            elif choice == "5":
                if len(parts) < 2:
                    print("Usage: 6 brightness  (0-100)")
                else:
                    try:
                        br = int(parts[1])
                        brgb.set_brightness(br)
                        emit("actuator", "BRGB_BRIGHTNESS", brgb.get(), None, bool(rgb_cfg.get("simulated", default_simulated)))
                        print(f"[BRGB] BRIGHTNESS {br}")
                    except ValueError:
                        print("Invalid number.")

            elif choice == "6":
                text = raw[len("5"):].strip()
                if not text:
                    print("Usage: 5 any text")
                else:
                    lcd.show(text)
                    emit("actuator", "LCD", text, None, bool(lcd_cfg.get("simulated", default_simulated)))
                    print("[LCD] updated")

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
            brgb.cleanup()
        except Exception:
            pass
        try:
            GPIO.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()
