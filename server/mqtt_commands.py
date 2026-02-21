from __future__ import annotations

import json
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt


class MqttCommandPublisher:
    def __init__(self, broker: str, port: int, client_id: str, topic_prefix: str) -> None:
        self._broker = broker
        self._port = int(port)
        self._client_id = client_id
        self._topic_prefix = topic_prefix.rstrip("/")

        # IMPORTANT: create client here so _cli exists
        self._cli = mqtt.Client(client_id=self._client_id, clean_session=True)
        self._connected = False

        # optional callbacks
        self._cli.on_connect = self._on_connect
        self._cli.on_disconnect = self._on_disconnect

        # connect + loop
        self._cli.connect(self._broker, self._port, keepalive=60)
        self._cli.loop_start()

    def _on_connect(self, _client, _userdata, _flags, rc):
        self._connected = (rc == 0)

    def _on_disconnect(self, _client, _userdata, rc):
        self._connected = False

    def _topic(self, device: str) -> str:
        return f"{self._topic_prefix}/{device}/cmd"

    def _pub(self, device: str, msg: Dict[str, Any]) -> None:
        # If needed, you can re-connect here, but usually not necessary in dev
        payload = json.dumps(msg)
        self._cli.publish(self._topic(device), payload, qos=0, retain=False)

    # ---- Alarm (if you already use this somewhere) ----
    def publish_alarm(self, device: str, active: bool, reason: Optional[str] = None) -> None:
        self._pub(device, {"type": "ALARM_SET", "active": bool(active), "reason": reason})

    # ---- Timer / BTN commands ----
    def publish_timer_set(self, device: str, seconds: int) -> None:
        self._pub(device, {"type": "TIMER_SET", "seconds": int(seconds)})

    def publish_timer_run(self, device: str, running: bool) -> None:
        self._pub(device, {"type": "TIMER_RUN", "running": bool(running)})

    def publish_timer_reset(self, device: str) -> None:
        self._pub(device, {"type": "TIMER_RESET"})

    def publish_timer_add_seconds_config(self, device: str, add_seconds: int) -> None:
        self._pub(device, {"type": "TIMER_ADD_CONFIG", "addSeconds": int(add_seconds)})

    def publish_btn_press(self, device: str) -> None:
        self._pub(device, {"type": "BTN_PRESS"})