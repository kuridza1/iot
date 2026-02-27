from __future__ import annotations

import json
import os
import threading
import time
from typing import Dict, Any, Optional

import paho.mqtt.client as mqtt

from helper.helper import GPIO
from helper.settings import load_settings
from helper.telemetry import TelemetryEvent, now_ts
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


def _to_int01(v: Any) -> int:
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return 1 if int(v) != 0 else 0
    s = str(v).strip().lower()
    return 1 if s in ("1", "true", "t", "yes", "y", "on") else 0


def main() -> None:
    print(f"[{ts_str()}] PI3 main starting. pid={os.getpid()}")

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

    def emit(kind: str, code: str, value: Any, unit: Optional[str], simulated: bool) -> None:
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

    rgb_cfg = cfg.get("BRGB", {"simulated": default_simulated})
    lcd_cfg = cfg.get("LCD", {"simulated": default_simulated})

    rgb_sim = bool(rgb_cfg.get("simulated", default_simulated))
    lcd_sim = bool(lcd_cfg.get("simulated", default_simulated))

    brgb = BRGB(
        simulated=rgb_sim,
        pin_r=int(rgb_cfg.get("pin_r", 17)),
        pin_g=int(rgb_cfg.get("pin_g", 27)),
        pin_b=int(rgb_cfg.get("pin_b", 22)),
        active_high=bool(rgb_cfg.get("active_high", True)),
    )

    lcd = Lcd(
        simulated=lcd_sim,
        address=int(lcd_cfg.get("address", 0x27)),
    )

    lcd_enabled = True

    dpir_cfg = cfg.get(
        "DPIR3",
        {"delay_sec": 1.5, "simulated": default_simulated, "pin": 17, "pull": "down", "active_high": True},
    )

    dpir_sim = bool(dpir_cfg.get("simulated", default_simulated))
    dpir_pin = int(dpir_cfg.get("pin", 17))
    dpir_pull = str(dpir_cfg.get("pull", "down"))
    dpir_active_high = bool(dpir_cfg.get("active_high", True))
    def on_dpir3(motion: bool) -> None:
        m = bool(motion)
        emit("sensor", "DPIR3", m, None, dpir_sim)

        if not m:
            return

        with people_lock:
            p = int(people_inside)

        if p <= 0:
            payload = {
                "device": pi1_id,
                "cmd": "ALARM_SET",
                "value": {
                    "active": True,
                    "reason": "MOTION_WHEN_EMPTY",
                    "source": pi_id,
                    "meta": {"pir": "DPIR3", "people_inside": p},
                },
            }
            try:
                pub_client.publish(pi1_cmd_topic, json.dumps(payload), qos=1, retain=False)
                emit("security", "INCIDENT", "MOTION_WHEN_EMPTY", None, True)
            except Exception as e:
                emit("security", "INCIDENT_PUBLISH_FAIL", str(e), None, True)

    t = threading.Thread(
        target=run_pir_loop,
        args=(
            float(dpir_cfg.get("delay_sec", 1.5)),
            on_dpir3,
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

    rotate_period = float(lcd_cfg.get("rotate_period_sec", 2.5))

    lcd_lock = threading.Lock()
    latest: Dict[str, Dict[str, Optional[float]]] = {
        "DHT1": {"t": None, "h": None},
        "DHT2": {"t": None, "h": None},
        "DHT3": {"t": None, "h": None},
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

            url = f"{server_base}/telemetry/latest?device={device}&code={code}"
            with urllib.request.urlopen(url, timeout=1.0) as r:
                data = json.loads(r.read().decode("utf-8"))
            v = data.get("value", None)
            if v is None:
                return None
            return float(v)
        except Exception:
            return None
    people_device = str(server_cfg.get("people_device", "PI1")) 
    people_code = str(server_cfg.get("people_code", "PEOPLE_INSIDE"))

    people_lock = threading.Lock()
    people_inside: int = 0

    def fetch_latest_int(device: str, code: str) -> Optional[int]:
        v = fetch_latest(device, code)
        if v is None:
            return None
        try:
            return int(float(v))
        except Exception:
            return None

    def people_poll_loop() -> None:
        nonlocal people_inside
        while not stop_event.is_set():
            v = fetch_latest_int(people_device, people_code)
            if v is not None:
                with people_lock:
                    people_inside = v

            time.sleep(1.0)  
    order = ["DHT1", "DHT2", "DHT3"]
    idx = 0

    def render_screen(name: str, tval: Optional[float], hval: Optional[float]) -> str:
        if tval is None or hval is None:
            return f"{name}\nNo data"
        return f"{name} T:{tval:4.1f}C\nH:{hval:4.1f}%"

    def refresh_lcd_once() -> str:
        nonlocal idx

        name = order[idx % len(order)] 
        if name == "DHT3":
            t3 = fetch_latest(dht3_device, "DHT3_TEMP")
            h3 = fetch_latest(dht3_device, "DHT3_HUM")
            with lcd_lock:
                if t3 is not None:
                    latest["DHT3"]["t"] = t3
                if h3 is not None:
                    latest["DHT3"]["h"] = h3

        with lcd_lock:
            tval = latest[name]["t"]
            hval = latest[name]["h"]

        text = render_screen(name, tval, hval)

        if lcd_enabled:
            lcd.show(text)

        emit("actuator", "LCD_TEXT", text, None, lcd_sim)

        return text

    def lcd_rotate_loop() -> None:
        nonlocal idx
        while not stop_event.is_set():
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
                tval = latest[name]["t"]
                hval = latest[name]["h"]

            text = render_screen(name, tval, hval)

            if lcd_enabled:
                lcd.show(text)

            emit("actuator", "LCD_TEXT", text, None, lcd_sim)

            time.sleep(rotate_period)

    lcd_rotate_started = False
    lcd_rotate_lock = threading.Lock()
    with lcd_rotate_lock:
        if not lcd_rotate_started:
            lcd_rotate_started = True
            print(f"[{ts_str()}] LCD rotate loop starting (period={rotate_period:.2f}s)")
            threading.Thread(target=lcd_rotate_loop, daemon=True).start()
            threading.Thread(target=people_poll_loop, daemon=True).start()

    threading.Thread(
        target=run_dht_loop,
        args=(
            float(dht1_cfg.get("delay_sec", 3.0)),
            float(dht1_cfg.get("temp_c_start", 22.0)),
            float(dht1_cfg.get("hum_pct_start", 45.0)),
            lambda tval, hval: (
                set_dht("DHT1", tval, hval),
                emit("sensor", "DHT1_TEMP", float(tval), "C", bool(dht1_cfg.get("simulated", default_simulated))),
                emit("sensor", "DHT1_HUM", float(hval), "%", bool(dht1_cfg.get("simulated", default_simulated))),
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
            lambda tval, hval: (
                set_dht("DHT2", tval, hval),
                emit("sensor", "DHT2_TEMP", float(tval), "C", bool(dht2_cfg.get("simulated", default_simulated))),
                emit("sensor", "DHT2_HUM", float(hval), "%", bool(dht2_cfg.get("simulated", default_simulated))),
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

    broker = str(mqtt_cfg.get("broker", "localhost"))
    port = int(mqtt_cfg.get("port", 1883))
    topic_prefix = str(mqtt_cfg.get("topic_prefix", "")).strip().rstrip("/")
    cmd_topic = f"{topic_prefix}/{pi_id}/cmd" if topic_prefix else f"{pi_id}/cmd"
    pi1_id = str(server_cfg.get("alarm_device", "PI1")).strip()
    pi1_cmd_topic = f"{topic_prefix}/{pi1_id}/cmd" if topic_prefix else f"{pi1_id}/cmd"

    pub_client = mqtt.Client(client_id=f"{pi_id}-pub")

    try:
        pub_client.connect(broker, port, keepalive=30)
        pub_client.loop_start()
        print(f"[{ts_str()}] PI3 publisher connected (for PI1 cmds): topic={pi1_cmd_topic}")
    except Exception as e:
        print(f"[{ts_str()}] WARNING: pub client failed to start: {e}")

    def _handle_cmd(cmd: str, value: Any) -> None:
        nonlocal lcd_enabled
        cmd = str(cmd or "").strip()
        value = value if isinstance(value, dict) else {}

        if cmd in ("BRGB_SET", "PI3_BRGB_SET"):
            r = bool(_to_int01(value.get("r", 0)))
            g = bool(_to_int01(value.get("g", 0)))
            b = bool(_to_int01(value.get("b", 0)))

            print(f"[{ts_str()}] FRONTEND CMD {cmd}: r={r} g={g} b={b}")
            brgb.set(r, g, b)
            emit("actuator", "BRGB_SET", brgb.get(), None, rgb_sim)

        elif cmd in ("LCD_TOGGLE", "PI3_LCD_TOGGLE"):
            print(f"[{ts_str()}] FRONTEND CMD {cmd}")
            lcd_enabled = not lcd_enabled
            if not lcd_enabled:
                lcd.show("")
            else:
                refresh_lcd_once()
            emit("actuator", "LCD_ENABLED", lcd_enabled, None, lcd_sim)

        elif cmd in ("LCD_REFRESH", "PI3_LCD_REFRESH"):
            print(f"[{ts_str()}] FRONTEND CMD {cmd}")
            refresh_lcd_once()

        else:
            return

    def _on_cmd_msg(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except Exception:
            return

        dev = str(data.get("device", "")).strip()
        if dev and dev.upper() != pi_id.upper():
            return

        cmd = data.get("cmd", "")
        value = data.get("value", {})
        _handle_cmd(cmd, value)

    cmd_client = mqtt.Client(client_id=f"{pi_id}-cmd")
    cmd_client.on_message = _on_cmd_msg
    try:
        cmd_client.connect(broker, port, keepalive=30)
        cmd_client.subscribe(cmd_topic)
        cmd_client.loop_start()
        print(f"[{ts_str()}] PI3 subscribed to commands: {cmd_topic}")
    except Exception as e:
        print(f"[{ts_str()}] WARNING: cmd listener failed to start: {e}")

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
                emit("actuator", "BRGB", brgb.get(), None, rgb_sim)
                print(f"[BRGB] {'ON' if brgb.isOn() else 'OFF'}")

            elif choice == "3":
                try:
                    r, g, b = map(int, input("r g b (0/1): ").split())
                    brgb.set(bool(r), bool(g), bool(b))
                    emit("actuator", "BRGB_SET", brgb.get(), None, rgb_sim)
                    print(f"[BRGB] SET r={bool(r)} g={bool(g)} b={bool(b)}")
                except Exception:
                    print("Invalid input. Example: 1 0 1")

            elif choice == "4":
                lcd_enabled = not lcd_enabled
                if not lcd_enabled:
                    lcd.show("")  # blank
                else:
                    refresh_lcd_once()
                emit("actuator", "LCD_ENABLED", lcd_enabled, None, lcd_sim)
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
            cmd_client.loop_stop()
            cmd_client.disconnect()
        except Exception:
            pass
        try:
            pub_client.loop_stop()
            pub_client.disconnect()
        except Exception:
            pass
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