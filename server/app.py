from __future__ import annotations

from flask import Flask, jsonify
from influx_writer import InfluxWriter
from mqtt_to_influx import MqttToInfluxService
from mqtt_commands import MqttCommandPublisher
from alarm_service import AlarmService
from config import (
    INFLUX_BUCKET, INFLUX_ORG, INFLUX_TOKEN, INFLUX_URL,
    MQTT_CLIENT_ID, MQTT_BROKER, MQTT_PORT, MQTT_TOPIC_FILTER,
    MQTT_TOPIC_PREFIX, ALARM_PIN
)

app = Flask(__name__)

influx = InfluxWriter(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG, bucket=INFLUX_BUCKET)

cmd_pub = MqttCommandPublisher(
    broker=MQTT_BROKER,
    port=MQTT_PORT,
    client_id=f"{MQTT_CLIENT_ID}-cmd",
    topic_prefix=MQTT_TOPIC_PREFIX,
)

alarm = AlarmService(influx=influx, cmd=cmd_pub, alarm_pin=ALARM_PIN)

bridge = MqttToInfluxService(
    broker=MQTT_BROKER,
    port=MQTT_PORT,
    topic_filter=MQTT_TOPIC_FILTER,
    client_id=MQTT_CLIENT_ID,
    influx=influx,
    on_event=alarm.on_event,   
)
bridge.start()

@app.get("/health")
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
