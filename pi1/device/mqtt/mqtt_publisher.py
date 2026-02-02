from __future__ import annotations

import json
import threading
import time
from queue import Queue, Empty
from typing import Any, Dict, Optional, List

import paho.mqtt.client as mqtt

from device.telemetry import TelemetryEvent


class MqttBatchPublisher:
    """@brief Daemon publisher that sends events in batches to MQTT.

    Uses Queue (thread-safe) to avoid manual mutex locks and deadlocks.
    """

    def __init__(self, mqtt_cfg: Dict[str, Any]) -> None:
        self._enabled = bool(mqtt_cfg.get("enabled", True))
        self._broker = str(mqtt_cfg.get("broker", "localhost"))
        self._port = int(mqtt_cfg.get("port", 1883))
        self._topic_prefix = str(mqtt_cfg.get("topic_prefix", "iot/smart-house"))
        self._client_id = str(mqtt_cfg.get("client_id", "pi-client"))
        self._qos = int(mqtt_cfg.get("qos", 1))
        self._retain = bool(mqtt_cfg.get("retain", False))
        self._batch_size = int(mqtt_cfg.get("batch_size", 10))
        self._flush_interval = float(mqtt_cfg.get("flush_interval_sec", 5))

        self._q: "Queue[TelemetryEvent]" = Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._client = mqtt.Client(client_id=self._client_id, clean_session=True)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        self._connected = False
        self._connected_lock = threading.Lock()

    def start(self) -> None:
        if not self._enabled:
            return
        # network loop in background thread managed by paho
        self._client.connect(self._broker, self._port, keepalive=60)
        self._client.loop_start()

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._enabled:
            try:
                self._client.loop_stop()
            except Exception:
                pass
            try:
                self._client.disconnect()
            except Exception:
                pass

    def enqueue(self, ev: TelemetryEvent) -> None:
        if not self._enabled:
            return
        self._q.put(ev)

    @property
    def topic_prefix(self) -> str:
        return self._topic_prefix

    def _on_connect(self, client, userdata, flags, rc) -> None:
        with self._connected_lock:
            self._connected = (rc == 0)

    def _on_disconnect(self, client, userdata, rc) -> None:
        with self._connected_lock:
            self._connected = False

    def _is_connected(self) -> bool:
        with self._connected_lock:
            return self._connected

    def _run(self) -> None:
        batch: List[TelemetryEvent] = []
        last_flush = time.time()

        while not self._stop.is_set():
            # Wait a bit for events; flush on timeout or when batch is full
            timeout = max(0.1, self._flush_interval / 2.0)
            try:
                ev = self._q.get(timeout=timeout)
                batch.append(ev)
            except Empty:
                pass

            now = time.time()
            should_flush = (
                len(batch) >= self._batch_size
                or (batch and (now - last_flush) >= self._flush_interval)
            )

            if should_flush:
                self._flush(batch)
                batch.clear()
                last_flush = now

        # final flush
        if batch:
            self._flush(batch)

    def _flush(self, events: List[TelemetryEvent]) -> None:
        if not events:
            return

        # If broker is down, we still don't want deadlock; we just try publish.
        # Keep critical section minimal: no locks around queue; only paho call.
        for ev in events:
            topic = ev.default_topic(self._topic_prefix)
            payload = json.dumps(ev.to_payload(), ensure_ascii=False)
            try:
                # publish is thread-safe with loop_start, but keep it simple
                self._client.publish(topic, payload, qos=self._qos, retain=self._retain)
            except Exception:
                # optionally: you can log to console; avoid blocking
                pass
