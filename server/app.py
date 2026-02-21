from __future__ import annotations

import queue
import time
from typing import Any, Dict, Tuple, List

from flask import Flask, Response, json, jsonify, request, stream_with_context
from flask_cors import CORS
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
CORS(app)
influx = InfluxWriter(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, bucket=INFLUX_BUCKET)
reader = InfluxReader(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, bucket=INFLUX_BUCKET)

cmd_pub = MqttCommandPublisher(
    broker=MQTT_BROKER,
    port=MQTT_PORT,
    client_id=f"{MQTT_CLIENT_ID}-cmd",
    topic_prefix=MQTT_TOPIC_PREFIX,
)

alarm = AlarmService(influx=influx, cmd=cmd_pub, alarm_pin=ALARM_PIN)


latest: Dict[Tuple[str, str], Dict[str, Any]] = {}
subs: List[queue.Queue] = []


def _to_dict(ev: Any) -> Dict[str, Any]:
    if isinstance(ev, dict):
        return ev
    if hasattr(ev, "__dict__"):
        return dict(ev.__dict__)
    return {"value": ev}


def _publish_update(ev_dict: Dict[str, Any]) -> None:
    device = str(ev_dict.get("device", "unknown"))
    code = str(ev_dict.get("code", ""))
    if code:
        latest[(device, code)] = ev_dict

    dead: List[queue.Queue] = []
    for q in subs:
        try:
            q.put_nowait(ev_dict)
        except Exception:
            dead.append(q)
    for q in dead:
        try:
            subs.remove(q)
        except ValueError:
            pass

def on_event_all(ev: Any) -> None:
    d = _to_dict(ev)
    alarm.on_event(d)
    _publish_update(d)

bridge = MqttToInfluxService(
    broker=MQTT_BROKER,
    port=MQTT_PORT,
    topic_filter=MQTT_TOPIC_FILTER,
    client_id=MQTT_CLIENT_ID,
    influx=influx,
    on_event=on_event_all,
)
bridge.start()


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/alarm/disarm")
def alarm_disarm():
    data = request.get_json(force=True) or {}
    device = str(data.get("device", "PI2"))
    pin = str(data.get("pin", ""))

    if pin != ALARM_PIN:
        return jsonify({"error": "bad pin"}), 403

    alarm.set_alarm(device, device_name=device, active=False, reason="WEB_PIN_OK")
    alarm.set_armed(device, device_name=device, armed=False, reason="WEB_PIN_OK")
    return jsonify({"ok": True})


# NOTE: this endpoint is numeric-only (your timer "4SD" is a string)
@app.get("/telemetry/latest")
def telemetry_latest():
    device = request.args.get("device", "PI2")
    code = request.args.get("code", "")
    if not code:
        return jsonify({"error": "missing code"}), 400

    v = reader.latest_num(device=device, code=code, lookback="30m")
    return jsonify({"device": device, "code": code, "value": v})


@app.get("/telemetry/state")
def telemetry_state():
    device = request.args.get("device", "PI2")
    codes_raw = request.args.get("codes", "")
    if not codes_raw:
        return jsonify({"error": "missing codes"}), 400

    codes = [c.strip() for c in codes_raw.split(",") if c.strip()]
    out: Dict[str, Any] = {}
    for code in codes:
        out[code] = latest.get((device, code))
    return jsonify({"device": device, "state": out})


@app.get("/events")
def events():
    q: queue.Queue = queue.Queue(maxsize=200)
    subs.append(q)

    @stream_with_context
    def gen():
        snapshot = {f"{dev}:{code}": val for (dev, code), val in latest.items()}
        yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"

        while True:
            try:
                ev = q.get(timeout=25)
                yield f"data: {json.dumps(ev)}\n\n"
            except queue.Empty:
                yield "event: ping\ndata: {}\n\n"

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.post("/pi2/timer/set")
def pi2_timer_set():
    data = request.get_json(force=True) or {}
    device = str(data.get("device", "PI2"))
    seconds = int(float(data.get("seconds", 0)))
    cmd_pub.publish_timer_set(device, seconds)
    return jsonify({"ok": True})

@app.post("/pi2/timer/run")
def pi2_timer_run():
    data = request.get_json(force=True) or {}
    device = str(data.get("device", "PI2"))
    running = bool(data.get("running", True))
    cmd_pub.publish_timer_run(device, running)
    return jsonify({"ok": True})

@app.post("/pi2/timer/reset")
def pi2_timer_reset():
    data = request.get_json(force=True) or {}
    device = str(data.get("device", "PI2"))
    cmd_pub.publish_timer_reset(device)
    return jsonify({"ok": True})

@app.post("/pi2/timer/add-seconds-config")
def pi2_timer_add_seconds_config():
    data = request.get_json(force=True) or {}
    device = str(data.get("device", "PI2"))
    add_seconds = int(float(data.get("addSeconds", 5)))
    cmd_pub.publish_timer_add_seconds_config(device, add_seconds)
    return jsonify({"ok": True})

@app.post("/pi2/btn/press")
def pi2_btn_press():
    data = request.get_json(force=True) or {}
    device = str(data.get("device", "PI2"))
    cmd_pub.publish_btn_press(device)
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded= True)