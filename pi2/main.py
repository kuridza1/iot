from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict

import paho.mqtt.client as mqtt

from actuators import button as button_mod
from actuators.button import Button
from actuators.four_digit_timer import FourDigitTimer

from helper.helper import GPIO
from helper.settings import load_settings
from helper.emit import make_emitter
from mqtt.mqtt_publisher import MqttBatchPublisher

from sensors.pir import run_pir_loop
from sensors.ultrasonic import run_ultrasonic_loop
from sensors.gsg import run_gsg_loop
from sensors.dht import run_dht_loop
from sensors.timer import run_timer_loop
from sensors.btn import run_button_loop

from pi2.cmd_listener import Pi2CmdListener


def ts_str() -> str:
    return time.strftime("%H:%M:%S", time.localtime())


def main() -> None:
    cfg = load_settings("pi2/settings.json")
    stop_event = threading.Event()

    device_cfg = cfg.get("device", {})
    pi_id = str(device_cfg.get("pi_id", "PI2"))
    device_name = str(device_cfg.get("device_name", "Device"))
    default_simulated = bool(device_cfg.get("default_simulated", True))

    publisher = MqttBatchPublisher(cfg.get("mqtt", {}))
    publisher.start()

    emit, safe_print, set_suppress = make_emitter(
        publisher, device=pi_id, device_name=device_name, ts_str=ts_str
    )

    # ---------------- DS2 / BTN / TIMER ----------------
    ds2_cfg = cfg.get("DS2", {"simulated": default_simulated, "pin": 23, "active_high": True})
    btn_cfg = cfg.get("BTN", {"simulated": default_simulated, "pin": 24, "active_high": True})
    timer_cfg = cfg.get("4SD", {"simulated": default_simulated})

    ds2_sim = bool(ds2_cfg.get("simulated", default_simulated))
    btn_sim = bool(btn_cfg.get("simulated", default_simulated))
    timer_sim = bool(timer_cfg.get("simulated", default_simulated))

    ds2 = Button(**ds2_cfg)
    btn = Button(**btn_cfg)
    timer = FourDigitTimer(simulated=timer_sim)

    btn_add_seconds_ref: Dict[str, Any] = {"value": int(cfg.get("BTN_ADD_SECONDS", 0))}

    def emit_timer_state(reason: str) -> None:
        running, left = timer.status()
        blink = bool(getattr(timer, "is_blinking", lambda: False)())
        emit("actuator", "4SD", timer.render(), None, timer_sim)
        emit("actuator", "4SD_REM", int(left), "sec", timer_sim)
        emit("actuator", "4SD_RUN", bool(running), None, timer_sim)
        emit("actuator", "4SD_BLINK", bool(blink), None, timer_sim)
        emit("actuator", "4SD_STATE_REASON", str(reason), None, timer_sim)

    # Initial telemetry
    emit("actuator", "DS2", bool(ds2.isOn()), None, ds2_sim)
    emit("sensor", "BTN", bool(btn.isOn()), None, btn_sim)
    emit_timer_state("BOOT")
    emit("actuator", "BTN_ADD_SEC", int(btn_add_seconds_ref["value"]), "sec", timer_sim)

    # ---------------- MQTT ----------------
    mqtt_cfg = cfg.get("mqtt", {})
    broker = str(mqtt_cfg.get("broker", "localhost"))
    port = int(mqtt_cfg.get("port", 1883))
    topic_prefix = str(mqtt_cfg.get("topic_prefix", "devices")).rstrip("/")

    # Listen for commands for PI2 (including DS2)
    cmd_listener = Pi2CmdListener(
        broker=broker,
        port=port,
        client_id=f"{pi_id}-cmd-listener",
        topic_prefix=topic_prefix,
        device=pi_id,
        timer=timer,
        emit=emit,
        stop_event=stop_event,
        timer_simulated=timer_sim,
        btn_add_seconds_ref=btn_add_seconds_ref,
        ds2_button=ds2,
        ds2_simulated=ds2_sim,
    )
    cmd_listener.start()

    # Publisher used for cross-device alarms (PI2 -> PI1), same as your GSG logic
    alarm_pub = mqtt.Client(client_id=f"{pi_id}-alarm-pub", clean_session=True)
    alarm_pub.connect(broker, port, keepalive=60)
    alarm_pub.loop_start()

    threads: list[threading.Thread] = []

    # ---------------- PIR ----------------
    dpir_cfg = cfg.get(
        "DPIR2",
        {"delay_sec": 1.5, "simulated": default_simulated, "pin": 17, "pull": "down", "active_high": True},
    )
    dpir_sim = bool(dpir_cfg.get("simulated", default_simulated))

    def on_pir(motion: bool) -> None:
        emit("sensor", "DPIR2", bool(motion), None, dpir_sim)

    t = threading.Thread(
        target=run_pir_loop,
        args=(
            float(dpir_cfg.get("delay_sec", 1.5)),
            on_pir,
            stop_event,
            dpir_sim,
            int(dpir_cfg.get("pin", 17)),
            str(dpir_cfg.get("pull", "down")),
            bool(dpir_cfg.get("active_high", True)),
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # ---------------- Ultrasonic ----------------
    dus_cfg = cfg.get("DUS2", {"delay_sec": 2.0, "simulated": default_simulated, "trig_pin": 5, "echo_pin": 6})
    dus_sim = bool(dus_cfg.get("simulated", default_simulated))

    t = threading.Thread(
        target=run_ultrasonic_loop,
        args=(
            float(dus_cfg.get("delay_sec", 2.0)),
            lambda d: emit("sensor", "DUS2", None if d is None else float(d), "cm", dus_sim),
            stop_event,
            dus_sim,
            int(dus_cfg.get("trig_pin", 5)),
            int(dus_cfg.get("echo_pin", 6)),
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # ---------------- GSG (existing) ----------------
    gsg_cfg = cfg.get("GSG", {"delay_sec": 0.5, "simulated": default_simulated, "threshold": 0.5})
    gsg_sim = bool(gsg_cfg.get("simulated", default_simulated))
    gsg_threshold = float(gsg_cfg.get("threshold", 0.5))

    alarm_cooldown_sec = float(gsg_cfg.get("alarm_cooldown_sec", 0.5))
    last_alarm_ts = 0.0

    def on_gsg(moving: bool, mag: float) -> None:
        nonlocal last_alarm_ts

        emit("sensor", "GSG", bool(moving), None, gsg_sim)
        emit("telemetry", "GSG_MAG", float(mag), None, gsg_sim)

        if moving:
            now = time.time()
            if (now - last_alarm_ts) >= alarm_cooldown_sec:
                topic = f"{topic_prefix}/PI1/cmd"
                payload = {
                    "cmd": "ALARM_SET",
                    "value": {"active": True, "reason": "GSG_MOVE", "magnitude": float(mag)},
                }
                alarm_pub.publish(topic, json.dumps(payload), qos=1, retain=False)
                last_alarm_ts = now

    t = threading.Thread(
        target=run_gsg_loop,
        args=(
            float(gsg_cfg.get("delay_sec", 0.5)),
            gsg_threshold,
            on_gsg,
            stop_event,
            gsg_sim,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # ---------------- DHT ----------------
    dht3_cfg = cfg.get("DHT3", {"delay_sec": 3.0, "simulated": default_simulated})
    dht3_sim = bool(dht3_cfg.get("simulated", default_simulated))

    t = threading.Thread(
        target=run_dht_loop,
        args=(
            float(dht3_cfg.get("delay_sec", 3.0)),
            float(dht3_cfg.get("temp_c_start", 22.0)),
            float(dht3_cfg.get("hum_pct_start", 45.0)),
            lambda temp_c, hum_pct: (
                emit("sensor", "DHT3_TEMP", float(temp_c), "C", dht3_sim),
                emit("sensor", "DHT3_HUM", float(hum_pct), "%", dht3_sim),
            ),
            stop_event,
        ),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # ---------------- BTN loop ----------------
    last_btn = False

    def on_btn(v: bool) -> None:
        nonlocal last_btn
        emit("sensor", "BTN", bool(v), None, btn_sim)
        if (not last_btn) and v:
            timer.stop_blink()
            add_sec = int(btn_add_seconds_ref["value"])
            timer.add(add_sec)
            emit("actuator", "4SD_ADD", add_sec, "sec", timer_sim)
            emit_timer_state("BTN_RISING_EDGE")
        last_btn = v

    t = threading.Thread(
        target=run_button_loop,
        args=(0.1, btn.isOn, on_btn, stop_event),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # ---------------- Timer loop ----------------
    def on_tick(text: str, rem: int) -> None:
        emit("actuator", "4SD", text, None, timer_sim)
        emit("actuator", "4SD_REM", int(rem), "sec", timer_sim)
        running, _ = timer.status()
        emit("actuator", "4SD_RUN", bool(running), None, timer_sim)
        blink = bool(getattr(timer, "is_blinking", lambda: False)())
        emit("actuator", "4SD_BLINK", bool(blink), None, timer_sim)

    def on_finished() -> None:
        emit("actuator", "4SD_FINISHED", True, None, timer_sim)
        emit_timer_state("FINISHED")

    t = threading.Thread(
        target=run_timer_loop,
        args=(timer, on_tick, on_finished, stop_event),
        daemon=True,
    )
    t.start()
    threads.append(t)

    # ---------------- NEW: DS2 HELD -> ALARM_SET to PI1 ----------------
    # This mirrors your GSG pattern: PI2 detects condition and publishes PI1/cmd.
    ds2_held_threshold_sec = float(cfg.get("DS2_HELD_THRESHOLD_SEC", 5.0))
    ds2_alarm_cooldown_sec = float(cfg.get("DS2_ALARM_COOLDOWN_SEC", 10.0))

    ds2_high_since: float | None = None
    ds2_held_triggered = False
    last_ds2_alarm_ts = 0.0
    last_ds2_state: bool | None = None

    def poll_ds2_held() -> None:
        nonlocal ds2_high_since, ds2_held_triggered, last_ds2_alarm_ts, last_ds2_state

        now = time.time()
        open_now = bool(ds2.isOn())  # "open/unlocked" per your convention

        # Emit state if it changes (helps Influx + UI even if command didn't produce emit)
        if last_ds2_state is None or open_now != last_ds2_state:
            emit("actuator", "DS2", open_now, None, ds2_sim)
            last_ds2_state = open_now

        if open_now:
            if ds2_high_since is None:
                ds2_high_since = now
                ds2_held_triggered = False

            if (not ds2_held_triggered) and (now - ds2_high_since) >= ds2_held_threshold_sec:
                # Cooldown so it doesn't spam PI1
                if (now - last_ds2_alarm_ts) >= ds2_alarm_cooldown_sec:
                    topic = f"{topic_prefix}/PI1/cmd"
                    payload = {
                        "cmd": "ALARM_SET",
                        "value": {"active": True, "reason": "DS2_HELD_5S", "threshold_sec": ds2_held_threshold_sec},
                    }
                    alarm_pub.publish(topic, json.dumps(payload), qos=1, retain=False)
                    last_ds2_alarm_ts = now
                ds2_held_triggered = True
        else:
            ds2_high_since = None
            ds2_held_triggered = False

    def ds2_held_loop() -> None:
        # fast enough to detect 5s reliably, not too heavy
        while not stop_event.is_set():
            try:
                poll_ds2_held()
            except Exception:
                pass
            time.sleep(0.2)

    t = threading.Thread(target=ds2_held_loop, daemon=True)
    t.start()
    threads.append(t)

    # ---------------- MAIN ----------------
    try:
        while not stop_event.is_set():
            time.sleep(1)
    finally:
        stop_event.set()

        try:
            cmd_listener.stop()
        except Exception:
            pass

        try:
            alarm_pub.loop_stop()
            alarm_pub.disconnect()
        except Exception:
            pass

        try:
            publisher.stop()
        except Exception:
            pass

        try:
            GPIO.cleanup()
        except Exception:
            pass

        try:
            ds2.cleanup()
        except Exception:
            pass
        try:
            btn.cleanup()
        except Exception:
            pass
        try:
            button_mod.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()