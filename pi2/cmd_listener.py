# pi2/cmd_listener.py
from __future__ import annotations

import json
import threading
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt


class Pi2CmdListener:
    """
    Same structure as PI1 PiCmdListener.
    Listens on: {topic_prefix}/{device}/cmd
    Expects JSON payload: {"cmd": "...", "value": ...}
    """

    def __init__(
        self,
        broker: str,
        port: int,
        client_id: str,
        topic_prefix: str,
        device: str,
        timer,              # FourDigitTimer
        emit,
        stop_event: threading.Event,
        timer_simulated: bool = True,
        # optional: BTN_ADD_SECONDS is part of PI2 state
        btn_add_seconds_ref: Optional[Dict[str, Any]] = None,  # {"value": int}
    ) -> None:
        self._topic = f"{topic_prefix.rstrip('/')}/{device}/cmd"
        self._timer = timer
        self._emit = emit
        self._stop_event = stop_event
        self._timer_sim = bool(timer_simulated)
        self._btn_add_ref = btn_add_seconds_ref

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

    def _emit_timer_state(self, reason: str) -> None:
        try:
            running, left = self._timer.status()
            blink = bool(getattr(self._timer, "is_blinking", lambda: False)())

            self._emit("actuator", "4SD", self._timer.render(), None, self._timer_sim)
            self._emit("actuator", "4SD_REM", int(left), "sec", self._timer_sim)
            self._emit("actuator", "4SD_RUN", bool(running), None, self._timer_sim)
            self._emit("actuator", "4SD_BLINK", bool(blink), None, self._timer_sim)
            self._emit("actuator", "4SD_STATE_REASON", str(reason), None, self._timer_sim)
        except Exception:
            pass

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

        # --- Timer commands (match server mappings) ---

        # TIMER_SET: value can be {"seconds": 60} or 60
        if cmd == "TIMER_SET":
            sec = 0
            if isinstance(value, dict):
                sec = int(float(value.get("seconds", 0)))
            else:
                sec = int(float(value or 0))
            self._timer.set(sec)
            self._emit("actuator", "4SD_SET", sec, "sec", self._timer_sim)
            self._emit_timer_state("CMD_TIMER_SET")
            return

        # TIMER_RUN: value can be {"running": true} or true/false
        if cmd == "TIMER_RUN":
            running = True
            if isinstance(value, dict):
                running = bool(value.get("running", True))
            else:
                running = bool(value)
            if running:
                self._timer.start()
            else:
                self._timer.stop()
            self._emit_timer_state("CMD_TIMER_RUN")
            return

        # TIMER_RESET
        if cmd == "TIMER_RESET":
            self._timer.reset()
            self._emit("actuator", "4SD_RESET", True, None, self._timer_sim)
            self._emit_timer_state("CMD_TIMER_RESET")
            return

        # TIMER_ADD_CONFIG: value {"addSeconds": 5} or 5
        if cmd == "TIMER_ADD_CONFIG":
            add_sec = 5
            if isinstance(value, dict):
                add_sec = int(float(value.get("addSeconds", 5)))
            else:
                add_sec = int(float(value or 5))

            if self._btn_add_ref is not None:
                self._btn_add_ref["value"] = add_sec

            self._emit("actuator", "BTN_ADD_SEC", int(add_sec), "sec", self._timer_sim)
            return

        # BTN_PRESS: add N sec and stop blinking
        if cmd == "BTN_PRESS":
            add_sec = 5
            if self._btn_add_ref is not None:
                add_sec = int(self._btn_add_ref.get("value", 5))

            self._timer.stop_blink()
            self._timer.add(add_sec)
            self._emit("actuator", "4SD_ADD", int(add_sec), "sec", self._timer_sim)
            self._emit_timer_state("CMD_BTN_PRESS")
            return