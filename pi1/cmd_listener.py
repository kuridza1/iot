from __future__ import annotations

import json
import threading
from typing import Any, Optional

import paho.mqtt.client as mqtt


class PiCmdListener:
    def __init__(
        self,
        broker: str,
        port: int,
        client_id: str,
        topic_prefix: str,
        device: str,
        alarm,
        led,
        buzzer,
        button,
        emit,
        stop_event: threading.Event,
        led_simulated: bool = True,
        buz_simulated: bool = True,
        btn_simulated: bool = True,
    ) -> None:
        self._topic = f"{topic_prefix.rstrip('/')}/{device}/cmd"
        self._alarm = alarm
        self._led = led
        self._buzzer = buzzer
        self._button = button
        self._emit = emit
        self._stop_event = stop_event

        self._led_sim = bool(led_simulated)
        self._buz_sim = bool(buz_simulated)
        self._btn_sim = bool(btn_simulated)

        self._client = mqtt.Client(client_id=client_id, clean_session=True)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(broker, int(port), keepalive=60)

    def start(self) -> None:
        self._client.loop_start()

    def stop(self) -> None:
        try:
            self._client.loop_stop()
        except Exception:
            pass
        try:
            self._client.disconnect()
        except Exception:
            pass

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            client.subscribe(self._topic, qos=1)

    def _on_message(self, client, userdata, msg) -> None:
        if self._stop_event.is_set():
            return

        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                return
        except Exception:
            return

        cmd = str(payload.get("cmd", "")).strip()
        value = payload.get("value", None)

        if cmd == "PIN_SUBMIT":
            pin = "" if value is None else str(value).strip()
            self._alarm.submit_pin(pin, source="FE")
            try:
                self._emit("security", "ALARM_STATE", self._alarm.state.value, None, True)
            except Exception:
                pass
            return

        if cmd == "DL":
            if bool(value):
                self._led.on()
            else:
                self._led.off()
            self._emit("actuator", "DL", self._led.isOn(), None, self._led_sim)
            return

        if cmd == "DB":
            if bool(value):
                self._buzzer.on()
            else:
                self._buzzer.off()
            self._emit("actuator", "DB", self._buzzer.isOn(), None, self._buz_sim)
            return

        if cmd == "DS1":
            if bool(value):
                self._button.on()
            else:
                self._button.off()
            self._emit("actuator", "DS1", self._button.isOn(), None, self._btn_sim)
            return

        if cmd == "ALARM":
            active = bool(value)
            if active:
                self._buzzer.on()
            else:
                self._buzzer.off()
            self._emit("actuator", "DB", self._buzzer.isOn(), None, self._buz_sim)
            return

        if cmd == "ALARM_SET":
            active = True
            reason = "GSG"
            magnitude = None

            if isinstance(value, dict):
                active = bool(value.get("active", True))
                reason = str(value.get("reason", reason))
                magnitude = value.get("magnitude", None)
            else:
                active = bool(value)

            if active:
                try:
                    self._alarm.trigger_alarm(reason=reason, source="MQTT", meta={"magnitude": magnitude})
                except Exception:
                    self._alarm.alarm_on(f"MQTT:{reason}")
            else:
                try:
                    self._alarm.clear_alarm(reason=reason, source="MQTT")
                except Exception:
                    self._alarm.disarm(f"MQTT:{reason}")

            try:
                self._emit("security", "ALARM_STATE", self._alarm.state.value, None, True)
            except Exception:
                pass
            return