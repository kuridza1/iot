from __future__ import annotations

import threading
import time
from typing import Dict, Any, Optional

from actuators import button
from actuators.button import Button
from actuators.four_digit_timer import FourDigitTimer

from mqtt.mqtt_publisher import MqttBatchPublisher
from helper.telemetry import TelemetryEvent, now_ts
from helper.helper import GPIO

from sensors.ultrasonic import run_ultrasonic_loop
from sensors.pir import run_pir_loop
from sensors.gsg import run_gsg_loop
from sensors.timer import run_timer_loop
from sensors.dht import run_dht_loop
from sensors.btn import run_button_loop

from helper.settings import load_settings

# You said you added the command listener already
# Expected signature:
# run_cmd_listener(broker, port, client_id, topic_prefix, device, on_cmd, stop_event)
from commands.pi2 import run_cmd_listener


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

    def emit_timer_state(reason: str) -> None:
        running, left = timer.status()
        emit("actuator", "4SD", timer.render(), None, timer_sim)
        emit("actuator", "4SD_REM", int(left), "sec", timer_sim)
        emit("actuator", "4SD_RUN", bool(running), None, timer_sim)
        emit("actuator", "4SD_STATE_REASON", str(reason), None, timer_sim)
    # ----------------------------
    # Components
    # ----------------------------
    ds2_cfg = cfg.get("DS2", {"simulated": default_simulated, "pin": 23, "active_high": True})
    btn_cfg = cfg.get("BTN", {"simulated": default_simulated, "pin": 24, "active_high": True})
    timer_cfg = cfg.get("4SD", {"simulated": default_simulated})

    ds2_sim = bool(ds2_cfg.get("simulated", default_simulated))
    btn_sim = bool(btn_cfg.get("simulated", default_simulated))
    timer_sim = bool(timer_cfg.get("simulated", default_simulated))

    ds2 = Button(
        simulated=ds2_sim,
        pin=int(ds2_cfg.get("pin", 23)),
        active_high=bool(ds2_cfg.get("active_high", True)),
    )

    btn = Button(
        simulated=btn_sim,
        pin=int(btn_cfg.get("pin", 24)),
        active_high=bool(btn_cfg.get("active_high", True)),
    )

    timer = FourDigitTimer(simulated=timer_sim)
    emit_timer_state("BOOT")
    emit("sensor", "BTN", bool(btn.isOn()), None, btn_sim)
    btn_add_seconds: int = int(cfg.get("BTN_ADD_SECONDS", 5))

    # ----------------------------
    # Sensors loops (as you had)
    # ----------------------------
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
        {"delay_sec": 2.0, "simulated": default_simulated, "trig_pin": 5, "echo_pin": 6},
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

    # ----------------------------
    # BTN loop: sends BTN state + on rising edge does:
    # - stop blinking
    # - add N seconds
    # ----------------------------
    last_btn = False

    def on_btn(v: bool) -> None:
        nonlocal last_btn, btn_add_seconds

        emit("sensor", "BTN", bool(v), None, btn_sim)

        # rising edge OFF->ON
        if (not last_btn) and v:
            timer.stop_blink()
            timer.add(btn_add_seconds)

            emit("actuator", "4SD_ADD", int(btn_add_seconds), "sec", timer_sim)

        last_btn = v

    t = threading.Thread(
        target=run_button_loop,
        args=(
            0.1,
            btn.isOn,
            on_btn,
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # ----------------------------
    # Timer loop: publishes display + remaining seconds; on finish emits FINISHED
    # FourDigitTimer itself handles blinking 00:00
    # ----------------------------
    t = threading.Thread(
        target=run_timer_loop,
        args=(
            timer,
            lambda text, rem: (
                emit("actuator", "4SD", text, None, timer_sim),
                emit("actuator", "4SD_REM", int(rem), "sec", timer_sim),
            ),
            lambda: emit("actuator", "4SD_FINISHED", True, None, timer_sim),
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # ----------------------------
    # MQTT command listener: Web -> Server -> MQTT cmd -> PI2 applies
    # ----------------------------
    broker = str(mqtt_cfg.get("broker", "mosquitto"))
    port = int(mqtt_cfg.get("port", 1883))
    topic_prefix = str(mqtt_cfg.get("topic_prefix", "iot/smart-house"))

    def apply_cmd(cmd: Dict[str, Any]) -> None:
        nonlocal btn_add_seconds

        t = str(cmd.get("type", ""))

        if t == "TIMER_SET":
            sec = int(float(cmd.get("seconds", 0)))
            timer.set(sec)
            emit("actuator", "4SD_SET", sec, "sec", timer_sim)
            emit_timer_state("CMD_TIMER_SET")

        elif t == "TIMER_RUN":
            running = bool(cmd.get("running", True))
            if running:
                timer.start()
            else:
                timer.stop()
            emit_timer_state("CMD_TIMER_RUN")

        elif t == "TIMER_RESET":
            timer.reset()
            emit("actuator", "4SD_RESET", True, None, timer_sim)
            emit_timer_state("CMD_TIMER_RESET")

        elif t == "TIMER_ADD_CONFIG":
            btn_add_seconds = int(float(cmd.get("addSeconds", 5)))
            emit("actuator", "BTN_ADD_SEC", btn_add_seconds, "sec", timer_sim)
            # ne mora emit_timer_state ovde

        elif t == "BTN_PRESS":
            timer.stop_blink()
            timer.add(btn_add_seconds)
            emit("actuator", "4SD_ADD", int(btn_add_seconds), "sec", timer_sim)
            emit_timer_state("CMD_BTN_PRESS")

    t = threading.Thread(
        target=run_cmd_listener,
        args=(
            broker,
            port,
            f"{pi_id}-cmd-sub",
            topic_prefix,
            pi_id,
            apply_cmd,
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # ----------------------------
    # Console menu (optional; keep for debugging)
    # ----------------------------
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
                print(f"BTN adds N seconds:     {btn_add_seconds}s")

            elif choice == "2":
                # DS2 is modeled using Button class; in simulation you can toggle it
                if ds2.isOn():
                    ds2.off()
                    emit("actuator", "DS2", False, None, ds2_sim)
                else:
                    ds2.on()
                    emit("actuator", "DS2", True, None, ds2_sim)

            elif choice == "3":
                # manual simulated press (toggle)
                if btn.isOn():
                    btn.off()
                    emit("sensor", "BTN", False, None, btn_sim)
                else:
                    btn.on()
                    emit("sensor", "BTN", True, None, btn_sim)

            elif choice == "4":
                if len(parts) < 2:
                    print("Usage: 4 <seconds>")
                else:
                    try:
                        sec = int(float(parts[1]))
                        timer.set(sec)
                        emit("actuator", "4SD_SET", sec, "sec", timer_sim)
                        print(f"[4SD] set to {sec}s ({timer.render()})")
                    except ValueError:
                        print("Invalid seconds.")

            elif choice == "5":
                running, _ = timer.status()
                if running:
                    timer.stop()
                    emit("actuator", "4SD_RUN", False, None, timer_sim)
                    print("[4SD] STOP")
                else:
                    timer.start()
                    emit("actuator", "4SD_RUN", True, None, timer_sim)
                    print("[4SD] START")

            elif choice == "6":
                timer.reset()
                emit("actuator", "4SD_RESET", True, None, timer_sim)
                print("[4SD] RESET")

            elif choice == "0":
                stop_event.set()

            else:
                print("Invalid option.")
                print_menu()

            time.sleep(0.05)

    finally:
        stop_event.set()
        time.sleep(0.2)
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