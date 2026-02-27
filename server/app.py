# server.py
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from flask import Flask, Response, jsonify, request
from flask_cors import CORS
import requests
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import make_response
from flask import Flask, Response, json, jsonify, request, stream_with_context
from flask_cors import CORS
from influx_writer import InfluxWriter
from influx_reader import InfluxReader
from mqtt_to_influx import MqttToInfluxService
from mqtt_commands import MqttCommandPublisher
from alarm_service import AlarmService
from config import (
    INFLUX_BUCKET,
    INFLUX_ORG,
    INFLUX_TOKEN,
    INFLUX_URL,
    MQTT_CLIENT_ID,
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_TOPIC_FILTER,
    MQTT_TOPIC_PREFIX,
    ALARM_PIN,
)

# -------------------- Flask + CORS --------------------
app = Flask(__name__)
CORS(
    app,
    resources={r"/*": {"origins": ["http://localhost:4200"]}},
    supports_credentials=False,
)

# -------------------- Socket.IO --------------------
# IMPORTANT:
# - Threading mode is the most robust with your current codebase (threads + blocking MQTT/IO).
# - Install: pip install flask-socketio
socketio = SocketIO(
    app,
    cors_allowed_origins=["http://localhost:4200"],
    async_mode="threading",
)

# -------------------- Core services --------------------
influx = InfluxWriter(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, bucket=INFLUX_BUCKET)
reader = InfluxReader(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, bucket=INFLUX_BUCKET)

cmd_pub = MqttCommandPublisher(
    broker=MQTT_BROKER,
    port=MQTT_PORT,
    client_id=f"{MQTT_CLIENT_ID}-cmd",
    topic_prefix=MQTT_TOPIC_PREFIX,
)

alarm = AlarmService()

# -------------------- Helpers --------------------
def _now_ts() -> float:
    return time.time()


def _snapshot_with_device(device: str) -> Dict[str, Any]:
    d = str(device).strip()
    snap = alarm.snapshot(d)
    if not isinstance(snap, dict):
        snap = {"data": snap}
    snap = dict(snap)
    snap["device"] = d
    return snap


def ws_emit_evt(evt: Any) -> None:
    if not isinstance(evt, dict):
        return
    evt = dict(evt)
    evt.setdefault("ts", _now_ts())
    device = str(evt.get("device", "")).strip()
    if not device:
        return
    socketio.emit("evt", evt, room=device)


def ws_emit_snapshot(device: str) -> None:
    device = str(device).strip()
    if not device:
        return
    socketio.emit("snapshot", _snapshot_with_device(device), room=device)


def ws_emit_pin_result(device: str, ok: bool, error: Optional[str] = None) -> None:
    device = str(device).strip()
    msg: Dict[str, Any] = {"device": device, "ok": bool(ok), "ts": _now_ts()}
    if error:
        msg["error"] = error
    socketio.emit("pin_result", msg, room=device)


def ws_emit_cmd_result(
    device: str,
    cmd: str,
    ok: bool,
    error: Optional[str] = None,
    value: Any = None,
) -> None:
    device = str(device).strip()
    msg: Dict[str, Any] = {"device": device, "cmd": str(cmd), "ok": bool(ok), "ts": _now_ts()}
    if error:
        msg["error"] = error
    if value is not None:
        msg["value"] = value
    socketio.emit("cmd_result", msg, room=device)


def on_event(payload: Any) -> None:
    if isinstance(payload, list):
        for item in payload:
            on_event(item)
        return

    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        for item in payload["events"]:
            on_event(item)
        return

    if not isinstance(payload, dict):
        return

    alarm.on_event(payload)   # passive cache
    ws_emit_evt(payload)      # push to FE

bridge = MqttToInfluxService(
    broker=MQTT_BROKER,
    port=MQTT_PORT,
    topic_filter=MQTT_TOPIC_FILTER,
    client_id=MQTT_CLIENT_ID,
    influx=influx,
    on_event=on_event,
)
bridge.start()

# -------------------- Socket.IO events --------------------
@socketio.on("connect")
def on_connect():
    device = str(request.args.get("device", "")).strip()
    if device:
        join_room(device)
        emit("snapshot", _snapshot_with_device(device))


@socketio.on("set_device")
def on_set_device(data):
    data = data or {}
    device = str(data.get("device", "PI1")).strip()

    # leave previous device rooms (keep sid)
    try:
        rooms = list(getattr(request, "rooms", []))
        for r in rooms:
            if r and r != request.sid:
                leave_room(r)
    except Exception:
        pass

    join_room(device)
    emit("snapshot", _snapshot_with_device(device))

ALLOWED_CMDS = {
    "PIN_SUBMIT", "DL", "DB", "ALARM_SET", "DS1",

    "PI3_BRGB_TOGGLE", "PI3_BRGB_SET",
    "BRGB_TOGGLE", "BRGB_SET",
    "TIMER_SET", "TIMER_RUN", "TIMER_RESET", "TIMER_ADD_CONFIG", "BTN_PRESS",

    "PI3_LCD_TOGGLE", "PI3_LCD_TEXT", "PI3_LCD_CLEAR", "PI3_LCD_REFRESH",
    "LCD_TOGGLE", "LCD_TEXT", "LCD_CLEAR", "LCD_REFRESH",
}

@socketio.on("cmd")
def on_ws_cmd(data):
    data = data or {}
    device = str(data.get("device", "")).strip()
    cmd_name = str(data.get("cmd", "")).strip()
    value = data.get("value", None)

    if not device or not cmd_name:
        ws_emit_cmd_result(device or "?", cmd_name or "?", False, "missing device/cmd")
        return

    if cmd_name not in ALLOWED_CMDS:
        ws_emit_cmd_result(device, cmd_name, False, "cmd not allowed")
        return

    try:
        cmd_pub.publish(device=device, cmd=cmd_name, value=value)
        ws_emit_cmd_result(device, cmd_name, True, None, value=value)
    except Exception as e:
        ws_emit_cmd_result(device, cmd_name, False, str(e))

# -------------------- HTTP routes --------------------
@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/state")
def state():
    device = request.args.get("device", "PI1")
    return jsonify(_snapshot_with_device(device))


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
        ws_emit_cmd_result(device or "?", cmd_name or "?", False, "missing device/cmd")
        return jsonify({"error": "missing device/cmd"}), 400

    if cmd_name not in ALLOWED_CMDS:
        ws_emit_cmd_result(device, cmd_name, False, "cmd not allowed")
        return jsonify({"error": "cmd not allowed"}), 400

    try:
        cmd_pub.publish(device=device, cmd=cmd_name, value=value)
        ws_emit_cmd_result(device, cmd_name, True, None, value=value)
        return jsonify({"ok": True})
    except Exception as e:
        ws_emit_cmd_result(device, cmd_name, False, str(e))
        return jsonify({"error": str(e)}), 500


@app.post("/alarm/pin")
def alarm_pin():
    data = request.get_json(silent=True) or {}
    device = str(data.get("device", "PI1")).strip()
    pin = str(data.get("pin", "")).strip()

    if not device or not pin:
        ws_emit_cmd_result(device or "?", "PIN_SUBMIT", False, "missing device/pin")
        return jsonify({"ok": False, "error": "missing device/pin"}), 400

    try:
        cmd_pub.publish(device=device, cmd="PIN_SUBMIT", value=pin)
        ws_emit_cmd_result(device, "PIN_SUBMIT", True, value={"pin_len": len(pin)})
        return jsonify({"ok": True})
    except Exception as e:
        ws_emit_cmd_result(device, "PIN_SUBMIT", False, str(e))
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/pi2/timer/set", methods=["POST", "OPTIONS"])
def pi2_timer_set():
    if request.method == "OPTIONS":
        return make_response(("", 200))

    data = request.get_json(silent=True) or {}
    device = str(data.get("device", "PI2")).strip()
    seconds = int(float(data.get("seconds", 0)))
    cmd_pub.publish(device=device, cmd="TIMER_SET", value={"seconds": seconds})
    ws_emit_cmd_result(device, "TIMER_SET", True, value={"seconds": seconds})
    return jsonify({"ok": True})

@app.post("/pi2/timer/run")
def pi2_timer_run():
    data = request.get_json(silent=True) or {}
    device = str(data.get("device", "PI2")).strip()
    running = bool(data.get("running", True))
    cmd_pub.publish(device=device, cmd="TIMER_RUN", value={"running": running})
    ws_emit_cmd_result(device, "TIMER_RUN", True, value={"running": running})
    return jsonify({"ok": True})

@app.post("/pi2/timer/reset")
def pi2_timer_reset():
    data = request.get_json(silent=True) or {}
    device = str(data.get("device", "PI2")).strip()
    cmd_pub.publish(device=device, cmd="TIMER_RESET", value=True) 

    ws_emit_cmd_result(device, "TIMER_RESET", True, value=True)
    return jsonify({"ok": True})

@app.post("/pi2/timer/add-seconds-config")
def pi2_timer_add_cfg():
    data = request.get_json(silent=True) or {}
    device = str(data.get("device", "PI2")).strip()
    add_seconds = int(float(data.get("addSeconds", 5)))
    cmd_pub.publish(device=device, cmd="TIMER_ADD_CONFIG", value={"addSeconds": add_seconds})
    ws_emit_cmd_result(device, "TIMER_ADD_CONFIG", True, value={"addSeconds": add_seconds})
    return jsonify({"ok": True})

@app.post("/pi2/btn/press")
def pi2_btn_press():
    data = request.get_json(silent=True) or {}
    device = str(data.get("device", "PI2")).strip()
    cmd_pub.publish(device=device, cmd="BTN_PRESS", value=True) 
    ws_emit_cmd_result(device, "BTN_PRESS", True, value=True)
    return jsonify({"ok": True})

CAMERA_URL = "http://PI1_IP:8080/?action=stream"

@app.route("/camera/pi1")
def camera_pi1():
    r = requests.get(CAMERA_URL, stream=True)

    return Response(
        r.iter_content(chunk_size=1024),
        content_type=r.headers["Content-Type"]
    )

# legacy SSE stub (optional)
@app.get("/events")
def events():
    return Response(
        "event: ping\ndata: {}\n\n",
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    # With async_mode="threading" this runs on Werkzeug (fine for local dev).
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
