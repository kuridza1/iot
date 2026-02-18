from __future__ import annotations
import json
import paho.mqtt.client as mqtt


class MqttCommandPublisher:
    def __init__(self, broker: str, port: int, client_id: str, topic_prefix: str) -> None:
        self._topic_prefix = topic_prefix.rstrip("/")
        self._client = mqtt.Client(client_id=client_id, clean_session=True)
        self._client.connect(broker, port, keepalive=60)
        self._client.loop_start()

    def publish_alarm(self, device: str, active: bool, reason: str | None = None) -> None:
        payload = {"cmd": "ALARM_SET", "value": bool(active)}
        if reason:
            payload["reason"] = str(reason)
        topic = f"{self._topic_prefix}/{device}/cmd"
        self._client.publish(topic, json.dumps(payload), qos=1, retain=False)

    def stop(self) -> None:
        try:
            self._client.loop_stop()
        except Exception:
            pass
        try:
            self._client.disconnect()
        except Exception:
            pass
