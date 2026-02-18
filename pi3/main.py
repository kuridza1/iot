import threading
import time
from typing import Dict, Any, Optional

from helper import GPIO
from settings import load_settings

from telemetry import TelemetryEvent, now_ts
from mqtt.mqtt_publisher import MqttBatchPublisher

from sensors.pir import run_pir_loop
from sensors.dht import run_dht_loop
from sensors.ir import run_ir_loop

from actuators.rgb import BRGB
from actuators.lcd.lcd import Lcd


def ts_str() -> str:
    return time.strftime("%H:%M:%S", time.localtime())


def print_menu() -> None:
    print("\n==== PI3 SMART ROOMS ====")
    print("1) Status")
    print("2) Toggle BRGB ON/OFF")
    print("3) Set BRGB (r g b) each 0/1  e.g. 1 0 1")
    print("4) Toggle LCD ON/OFF")
    print("5) Show LCD Display")
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

    # ---------- Actuators ----------
    rgb_cfg = cfg.get("BRGB", {"simulated": default_simulated})
    lcd_cfg = cfg.get("LCD", {"simulated": default_simulated})

    brgb = BRGB(
        simulated=bool(rgb_cfg.get("simulated", default_simulated)),
        pin_r=int(rgb_cfg.get("pin_r", 17)),
        pin_g=int(rgb_cfg.get("pin_g", 27)),
        pin_b=int(rgb_cfg.get("pin_b", 22)),
        active_high=bool(rgb_cfg.get("active_high", True)),
    )

    lcd = Lcd(simulated=bool(lcd_cfg.get("simulated", default_simulated)))

    # LCD enable/disable (logical)
    lcd_enabled = True

    # Rotation timing
    rotate_period = float(lcd_cfg.get("rotate_period_sec", 2.5))

    lcd_lock = threading.Lock()
    latest: Dict[str, Dict[str, Optional[float]]] = {
        "DHT1": {"t": None, "h": None},
        "DHT2": {"t": None, "h": None},
        "DHT3": {"t": None, "h": None},  # from server (PI2)
    }

    def set_dht(name: str, temp_c: float, hum_pct: float) -> None:
        with lcd_lock:
            latest[name]["t"] = float(temp_c)
            latest[name]["h"] = float(hum_pct)

    server_cfg = cfg.get("SERVER", {})
    server_base = str(server_cfg.get("base_url", "")).rstrip("/")
    dht3_device = str(server_cfg.get("dht3_device", "PI2"))

    def fetch_latest(device: str, code: str) -> Optional[float]:
        if not server_base:
            return None
        try:
            import urllib.request
            import json

            url = f"{server_base}/telemetry/latest?device={device}&code={code}"
            with urllib.request.urlopen(url, timeout=1.0) as r:
                data = json.loads(r.read().decode("utf-8"))
            v = data.get("value", None)
            if v is None:
                return None
            return float(v)
        except Exception:
            return None

    order = ["DHT1", "DHT2", "DHT3"]
    idx = 0

    def render_screen(name: str, t: Optional[float], h: Optional[float]) -> str:
        if t is None or h is None:
            return f"{name}\nNo data"
        return f"{name} T:{t:4.1f}C\nH:{h:4.1f}%"

    def refresh_lcd_once() -> str:
        nonlocal idx

        name = order[idx % len(order)]  # current screen (no advance)
        if name == "DHT3":
            t3 = fetch_latest(dht3_device, "DHT3_TEMP")
            h3 = fetch_latest(dht3_device, "DHT3_HUM")
            with lcd_lock:
                if t3 is not None:
                    latest["DHT3"]["t"] = t3
                if h3 is not None:
                    latest["DHT3"]["h"] = h3

        with lcd_lock:
            t = latest[name]["t"]
            h = latest[name]["h"]

        if t is None or h is None:
            text = f"{name}\nNo data"
        else:
            text = f"{name} T:{t:4.1f}C\nH:{h:4.1f}%"

        if lcd_enabled:
            lcd.show(text)

        return text

    def lcd_rotate_loop() -> None:
        nonlocal idx
        while not stop_event.is_set():
            # advance to next screen
            name = order[idx % len(order)]
            idx += 1

            if name == "DHT3":
                t3 = fetch_latest(dht3_device, "DHT3_TEMP")
                h3 = fetch_latest(dht3_device, "DHT3_HUM")
                with lcd_lock:
                    if t3 is not None:
                        latest["DHT3"]["t"] = t3
                    if h3 is not None:
                        latest["DHT3"]["h"] = h3

            with lcd_lock:
                t = latest[name]["t"]
                h = latest[name]["h"]

            if lcd_enabled:
                lcd.show(render_screen(name, t, h))

            time.sleep(rotate_period)

    threading.Thread(target=lcd_rotate_loop, daemon=True).start()

    dpir_cfg = cfg.get("DPIR3", {})
    dht1_cfg = cfg.get("DHT1", {})
    dht2_cfg = cfg.get("DHT2", {})
    ir_cfg = cfg.get("IR", {})

    threading.Thread(
        target=run_pir_loop,
        args=(
            float(dpir_cfg.get("delay_sec", 1.5)),
            lambda m: emit("sensor", "DPIR3", bool(m), None, bool(dpir_cfg.get("simulated", default_simulated))),
            stop_event,
            bool(dpir_cfg.get("simulated", default_simulated)),
            int(dpir_cfg.get("pin", 17)),
            str(dpir_cfg.get("pull", "down")),
            bool(dpir_cfg.get("active_high", True)),
        ),
        daemon=True,
    ).start()

    threading.Thread(
        target=run_dht_loop,
        args=(
            float(dht1_cfg.get("delay_sec", 3.0)),
            float(dht1_cfg.get("temp_c_start", 22.0)),
            float(dht1_cfg.get("hum_pct_start", 45.0)),
            lambda t, h: (
                set_dht("DHT1", t, h),
                emit("sensor", "DHT1_TEMP", float(t), "C", bool(dht1_cfg.get("simulated", default_simulated))),
                emit("sensor", "DHT1_HUM", float(h), "%", bool(dht1_cfg.get("simulated", default_simulated))),
            ),
            stop_event,
            bool(dht1_cfg.get("simulated", default_simulated)),
            int(dht1_cfg.get("pin", 4)),
        ),
        daemon=True,
    ).start()

    threading.Thread(
        target=run_dht_loop,
        args=(
            float(dht2_cfg.get("delay_sec", 3.0)),
            float(dht2_cfg.get("temp_c_start", 21.0)),
            float(dht2_cfg.get("hum_pct_start", 48.0)),
            lambda t, h: (
                set_dht("DHT2", t, h),
                emit("sensor", "DHT2_TEMP", float(t), "C", bool(dht2_cfg.get("simulated", default_simulated))),
                emit("sensor", "DHT2_HUM", float(h), "%", bool(dht2_cfg.get("simulated", default_simulated))),
            ),
            stop_event,
            bool(dht2_cfg.get("simulated", default_simulated)),
            int(dht2_cfg.get("pin", 5)),
        ),
        daemon=True,
    ).start()

    threading.Thread(
        target=run_ir_loop,
        args=(
            float(ir_cfg.get("delay_sec", 0.25)),
            float(ir_cfg.get("burst_prob", 0.06)),
            lambda c: emit("sensor", "IR", str(c), None, bool(ir_cfg.get("simulated", default_simulated))),
            stop_event,
            bool(ir_cfg.get("simulated", default_simulated)),
            int(ir_cfg.get("pin", 17)),
            None,
        ),
        daemon=True,
    ).start()

    print_menu()

    try:
        while not stop_event.is_set():
            choice = input("> ").strip()

            if choice == "1":
                st = brgb.get()
                print("\n--- STATUS ---")
                print(f"BRGB: {'ON' if brgb.isOn() else 'OFF'}  r={st['r']} g={st['g']} b={st['b']}")
                print(f"LCD:  {'ON' if lcd_enabled else 'OFF'}")

            elif choice == "2":
                if brgb.isOn():
                    brgb.off()
                else:
                    brgb.on()
                emit("actuator", "BRGB", brgb.get(), None, bool(rgb_cfg.get("simulated", default_simulated)))
                print(f"[BRGB] {'ON' if brgb.isOn() else 'OFF'}")

            elif choice == "3":
                try:
                    r, g, b = map(int, input("r g b (0/1): ").split())
                    brgb.set(bool(r), bool(g), bool(b))
                    emit("actuator", "BRGB_SET", brgb.get(), None, bool(rgb_cfg.get("simulated", default_simulated)))
                    print(f"[BRGB] SET r={bool(r)} g={bool(g)} b={bool(b)}")
                except Exception:
                    print("Invalid input. Example: 1 0 1")

            elif choice == "4":
                lcd_enabled = not lcd_enabled
                if not lcd_enabled:
                    lcd.show("")  # blank
                else:
                    refresh_lcd_once()
                emit("actuator", "LCD_ENABLED", lcd_enabled, None, bool(lcd_cfg.get("simulated", default_simulated)))
                print(f"[LCD] {'ON' if lcd_enabled else 'OFF'}")

            elif choice == "5":
                text = refresh_lcd_once()
                print(text)

            elif choice == "0":
                stop_event.set()

            else:
                print("Invalid option.")
                print_menu()

            time.sleep(0.05)

    finally:
        stop_event.set()
        time.sleep(0.1)

        try:
            publisher.stop()
        except Exception:
            pass

        try:
            lcd.cleanup()
        except Exception:
            pass

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
