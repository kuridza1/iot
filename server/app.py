from __future__ import annotations

from flask import Flask, jsonify, request

from influx_writer import InfluxWriter
from influx_reader import InfluxReader
from mqtt_to_influx import MqttToInfluxService
from config import (
    INFLUX_BUCKET, INFLUX_ORG, INFLUX_TOKEN, INFLUX_URL,
    MQTT_CLIENT_ID, MQTT_BROKER, MQTT_PORT, MQTT_TOPIC_FILTER
)

app = Flask(__name__)

influx = InfluxWriter(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, bucket=INFLUX_BUCKET)
reader = InfluxReader(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, bucket=INFLUX_BUCKET)

bridge = MqttToInfluxService(
    broker=MQTT_BROKER,
    port=MQTT_PORT,
    topic_filter=MQTT_TOPIC_FILTER,
    client_id=MQTT_CLIENT_ID,
    influx=influx,
)
bridge.start()


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/telemetry/latest")
def telemetry_latest():
    device = request.args.get("device", "PI2")
    code = request.args.get("code", "")
    if not code:
        return jsonify({"error": "missing code"}), 400

    v = reader.latest_num(device=device, code=code, lookback="30m")
    return jsonify({"device": device, "code": code, "value": v})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
