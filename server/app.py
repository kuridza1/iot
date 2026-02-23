from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Dict

from flask import Flask, Response, jsonify, request
from flask_cors import CORS
import requests
from influx_writer import InfluxWriter
from influx_reader import InfluxReader
from mqtt_to_influx import MqttToInfluxService
from mqtt_commands import MqttCommandPublisher
from alarm_service import AlarmService
from config import (
    INFLUX_BUCKET, INFLUX_ORG, INFLUX_TOKEN, INFLUX_URL,
    MQTT_CLIENT_ID, MQTT_BROKER, MQTT_PORT, MQTT_TOPIC_FILTER,
    MQTT_TOPIC_PREFIX, ALARM_PIN
)

app = Flask(__name__)
CORS(
    app,
    resources={r"/*": {"origins": ["http://localhost:4200"]}},
    supports_credentials=False,
)

subscribers_lock = threading.Lock()
subscribers: set["queue.Queue[Dict[str, Any]]"] = set()

def push_event(evt: Dict[str, Any]) -> None:
    evt = dict(evt)
    evt.setdefault("ts", time.time())

    with subscribers_lock:
        subs = list(subscribers)

    for q in subs:
        try:
            q.put_nowait(evt)
        except Exception:
            pass


influx = InfluxWriter(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, bucket=INFLUX_BUCKET)
reader = InfluxReader(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, bucket=INFLUX_BUCKET)

cmd_pub = MqttCommandPublisher(
    broker=MQTT_BROKER,
    port=MQTT_PORT,
    client_id=f"{MQTT_CLIENT_ID}-cmd",
    topic_prefix=MQTT_TOPIC_PREFIX,
)

alarm = AlarmService(influx=influx, cmd=cmd_pub, alarm_pin=ALARM_PIN)


def on_event(payload: Dict[str, Any]) -> None:
    # 1) server logika + cache state-a
    alarm.on_event(payload)
    # 2) live ka UI (SSE)
    push_event(payload)


bridge = MqttToInfluxService(
    broker=MQTT_BROKER,
    port=MQTT_PORT,
    topic_filter=MQTT_TOPIC_FILTER,
    client_id=MQTT_CLIENT_ID,
    influx=influx,
    on_event=on_event,
)
bridge.start()


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/state")
def state():
    device = request.args.get("device", "PI1")
    return jsonify(alarm.snapshot(device))


@app.get("/events")
def events():
    device = request.args.get("device", "PI1")

    client_q: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=1000)

    with subscribers_lock:
        subscribers.add(client_q)

    def gen():
        try:
            # inicijalni snapshot
            yield f"event: snapshot\ndata: {json.dumps(alarm.snapshot(device))}\n\n"

            last_ping = time.time()

            while True:
                try:
                    evt = client_q.get(timeout=1.0)
                except queue.Empty:
                    if time.time() - last_ping > 15.0:
                        yield "event: ping\ndata: {}\n\n"
                        last_ping = time.time()
                    continue

                if str(evt.get("device", "")) != str(device):
                    continue

                yield f"event: evt\ndata: {json.dumps(evt)}\n\n"
        finally:
            with subscribers_lock:
                subscribers.discard(client_q)

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/telemetry/latest")
def telemetry_latest():
    device = request.args.get("device", "PI2")
    code = request.args.get("code", "")
    if not code:
        return jsonify({"error": "missing code"}), 400

    v = reader.latest_num(device=device, code=code, lookback="30m")
    return jsonify({"device": device, "code": code, "value": v})


@app.post("/cmd")
def cmd():
    data = request.get_json(silent=True) or {}
    device = str(data.get("device", "")).strip()
    cmd_name = str(data.get("cmd", "")).strip()
    value = data.get("value", None)

    if not device or not cmd_name:
        return jsonify({"error": "missing device/cmd"}), 400

    allowed = {
        "PIN_SUBMIT",
        "DL",
        "DB",
        "ALARM_SET",
        "DS1",
    }
    if cmd_name not in allowed:
        return jsonify({"error": "cmd not allowed"}), 400

    cmd_pub.publish(device=device, cmd=cmd_name, value=value)
    return jsonify({"ok": True})


@app.post("/alarm/pin")
def alarm_pin():
    data = request.get_json(silent=True) or {}
    device = str(data.get("device", "PI1"))
    pin = str(data.get("pin", "")).strip()
    device_name = str(data.get("device_name", device))

    if len(pin) != 4 or not pin.isdigit():
        return jsonify({"ok": False, "error": "PIN must be 4 digits"}), 400

    ok = alarm.submit_pin(device=device, device_name=device_name, pin=pin, source="FE")

    cmd_pub.publish(device=device, cmd="PIN_SUBMIT", value=pin)

    return jsonify({"ok": ok})

CAMERA_URL = "http://PI1_IP:8080/?action=stream"

@app.route("/camera/pi1")
def camera_pi1():
    r = requests.get(CAMERA_URL, stream=True)

    return Response(
        r.iter_content(chunk_size=1024),
        content_type=r.headers["Content-Type"]
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)