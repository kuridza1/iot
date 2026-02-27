# pi2/main.py (aligned to PI1 main, with GSG magnitude + PI1 alarm trigger)
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

    # ----- MQTT publisher for telemetry/events (your existing pipeline) -----
    publisher = MqttBatchPublisher(cfg.get("mqtt", {}))
    publisher.start()

    emit, safe_print, set_suppress = make_emitter(
        publisher, device=pi_id, device_name=device_name, ts_str=ts_str
    )

    # ----- components -----
    ds2_cfg = cfg.get("DS2", {"simulated": default_simulated, "pin": 23, "active_high": True})
    btn_cfg = cfg.get("BTN", {"simulated": default_simulated, "pin": 24, "active_high": True})
    timer_cfg = cfg.get("4SD", {"simulated": default_simulated})

    ds2_sim = bool(ds2_cfg.get("simulated", default_simulated))
    btn_sim = bool(btn_cfg.get("simulated", default_simulated))
    timer_sim = bool(timer_cfg.get("simulated", default_simulated))

    ds2 = Button(**ds2_cfg)
    btn = Button(**btn_cfg)
    timer = FourDigitTimer(simulated=timer_sim)

    # state: BTN adds N seconds (shared between loops and cmd listener)
    btn_add_seconds_ref: Dict[str, Any] = {"value": int(cfg.get("BTN_ADD_SECONDS", 5))}

    def emit_timer_state(reason: str) -> None:
        running, left = timer.status()
        blink = bool(getattr(timer, "is_blinking", lambda: False)())
        emit("actuator", "4SD", timer.render(), None, timer_sim)
        emit("actuator", "4SD_REM", int(left), "sec", timer_sim)
        emit("actuator", "4SD_RUN", bool(running), None, timer_sim)
        emit("actuator", "4SD_BLINK", bool(blink), None, timer_sim)
        emit("actuator", "4SD_STATE_REASON", str(reason), None, timer_sim)

    # emit init immediately
    emit("sensor", "DS2", bool(ds2.isOn()), None, ds2_sim)
    emit("sensor", "BTN", bool(btn.isOn()), None, btn_sim)
    emit_timer_state("BOOT")
    emit("actuator", "BTN_ADD_SEC", int(btn_add_seconds_ref["value"]), "sec", timer_sim)

    # ----- MQTT command listener (front -> server -> mqtt -> pi2) -----
    mqtt_cfg = cfg.get("mqtt", {})
    broker = str(mqtt_cfg.get("broker", "localhost"))
    port = int(mqtt_cfg.get("port", 1883))
    topic_prefix = str(mqtt_cfg.get("topic_prefix", "devices")).rstrip("/")

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
    )
    cmd_listener.start()

    # ----- PI2 -> PI1 alarm publisher (for GSG threshold) -----
    alarm_pub = mqtt.Client(client_id=f"{pi_id}-alarm-pub", clean_session=True)
    alarm_pub.connect(broker, port, keepalive=60)
    alarm_pub.loop_start()

    # ----- loops -----
    threads: list[threading.Thread] = []

    # PIR
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

    # Ultrasonic
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

    # GSG (movement + magnitude) + trigger PI1 alarm on threshold
    gsg_cfg = cfg.get("GSG", {"delay_sec": 0.5, "simulated": default_simulated, "threshold": 0.5})
    gsg_sim = bool(gsg_cfg.get("simulated", default_simulated))
    gsg_threshold = float(gsg_cfg.get("threshold", 0.5))

    alarm_cooldown_sec = float(gsg_cfg.get("alarm_cooldown_sec", 5.0))
    last_alarm_ts = 0.0

    def on_gsg(moving: bool, mag: float) -> None:
        nonlocal last_alarm_ts

        # UI/telemetry
        emit("sensor", "GSG", bool(moving), None, gsg_sim)
        emit("telemetry", "GSG_MAG", float(mag), None, gsg_sim)

        # Trigger PI1 alarm only on "big move" and with cooldown
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

    # DHT3
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

    # BTN physical loop: rising edge => stop blink + add seconds
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

    # Timer loop: emits display + rem (+ finished)
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