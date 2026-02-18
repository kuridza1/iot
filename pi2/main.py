import threading
import time
from typing import Dict, Any, Optional

from actuators import button
from actuators.button import Button
from actuators.buzzer import Buzzer
from actuators.four_digit_timer import FourDigitTimer
from actuators.led import Led
from mqtt.mqtt_publisher import MqttBatchPublisher
from mqtt.mqtt_publisher import MqttBatchPublisher
from helper.telemetry import TelemetryEvent, now_ts
from helper.helper import GPIO

from sensors.ultrasonic import run_ultrasonic_loop
from sensors.pir import run_pir_loop
from sensors.gsg import run_gsg_loop
from sensors.timer import run_timer_loop
from sensors.dht import run_dht_loop

from helper.settings import load_settings

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
        if kind == "actuator":
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

    dpir_cfg = cfg.get("DPIR2", {"delay_sec": 1.5, "simulated": default_simulated, "pin": 17, "pull": "down", "active_high": True})

    dpir_sim = bool(dpir_cfg.get("simulated", default_simulated))
    dpir_pin = int(dpir_cfg.get("pin", 17))
    dpir_pull = str(dpir_cfg.get("pull", "down"))
    dpir_active_high = bool(dpir_cfg.get("active_high", True))

    t = threading.Thread(
        target=run_pir_loop,
        args=(
            float(dpir_cfg.get("delay_sec", 1.5)),
            lambda motion: emit("sensor", "DPIR2", bool(motion), None, dpir_sim),
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

    dus_cfg = cfg.get(
    "DUS2",
    {
        "delay_sec": 2.0,
        "simulated": default_simulated,
        "trig_pin": 5,
        "echo_pin": 6,
        },
    )

    dus_sim = bool(dus_cfg.get("simulated", default_simulated))
    dus_trig = int(dus_cfg.get("trig_pin", 5))
    dus_echo = int(dus_cfg.get("echo_pin", 6))

    t = threading.Thread(
        target=run_ultrasonic_loop,
        args=(
            float(dus_cfg.get("delay_sec", 2.0)),
            lambda d: emit("sensor", "DUS2", None if d is None else float(d), "cm", dus_sim),
            stop_event,
            dus_sim,
            dus_trig,
            dus_echo,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    gsg_cfg = cfg.get("GSG", {"delay_sec": 0.5, "simulated": default_simulated, "threshold": 0.5})

    gsg_sim = bool(gsg_cfg.get("simulated", default_simulated))
    gsg_threshold = float(gsg_cfg.get("threshold", 0.5))

    t = threading.Thread(
        target=run_gsg_loop,
        args=(
            float(gsg_cfg.get("delay_sec", 0.5)),
            gsg_threshold,
            lambda moving: emit("sensor", "GSG", bool(moving), None, gsg_sim),
            stop_event,
            gsg_sim,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    dht3_cfg = cfg.get("DHT3", {"delay_sec": 3.0, "simulated": default_simulated})

    # --- DHT3 loop: emits TEMP + HUM ---
    t = threading.Thread(
        target=run_dht_loop,
        args=(
            float(dht3_cfg.get("delay_sec", 3.0)),
            float(dht3_cfg.get("temp_c_start", 22.0)),
            float(dht3_cfg.get("hum_pct_start", 45.0)),
            lambda temp_c, hum_pct: (
                emit("sensor", "DHT3_TEMP", float(temp_c), "C", bool(dht3_cfg.get("simulated", default_simulated))),
                emit("sensor", "DHT3_HUM", float(hum_pct), "%", bool(dht3_cfg.get("simulated", default_simulated))),
            ),
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

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
                print("DHT3: publishing TEMP/HUM events")

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
        try:
            button.cleanup()
        except Exception:
            pass



if __name__ == "__main__":
    main()
