from __future__ import annotations

import json
import threading
from typing import Any, Dict, Optional, Callable

import paho.mqtt.client as mqtt

from influx_writer import InfluxWriter


class MqttToInfluxService:
    """@brief Subscribes to MQTT topics and writes payloads into InfluxDB."""

    def __init__(
        self,
        broker: str,
        port: int,
        topic_filter: str,
        client_id: str,
        influx: InfluxWriter,
    ) -> None:
        self._broker = broker
        self._port = port
        self._topic_filter = topic_filter
        self._client_id = client_id
        self._influx = influx

        self._client = mqtt.Client(client_id=self._client_id, clean_session=True)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def start(self) -> None:
        self._client.connect(self._broker, self._port, keepalive=60)
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
            client.subscribe(self._topic_filter, qos=1)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if isinstance(payload, dict):
                self._influx.write_event(payload)
        except Exception:
            # ignore malformed payloads
            pass
