from __future__ import annotations

import os
from flask import Flask, jsonify

from influx_writer import InfluxWriter
from mqtt_to_influx import MqttToInfluxService

app = Flask(__name__)

# ENV (keep secrets out of code)
INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "my-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "my-org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "iot")

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_FILTER = os.getenv("MQTT_TOPIC_FILTER", "iot/smart-house/#")
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "server-mqtt-influx")

influx = InfluxWriter(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, bucket=INFLUX_BUCKET)
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


if __name__ == "__main__":
    # Flask server just to satisfy requirement "implement server (Flask recommended)"
    # MQTT bridge runs regardless.
    app.run(host="0.0.0.0", port=5000, debug=False)
