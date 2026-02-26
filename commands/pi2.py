import json
import threading
from typing import Callable, Any, Dict
import paho.mqtt.client as mqtt

def run_cmd_listener(
    broker: str,
    port: int,
    client_id: str,
    topic_prefix: str,
    device: str,
    on_cmd: Callable[[Dict[str, Any]], None],
    stop_event: threading.Event,
) -> None:
    topic_prefix = topic_prefix.rstrip("/")
    topic = f"{topic_prefix}/{device}/cmd"

    cli = mqtt.Client(client_id=client_id, clean_session=True)

    def on_message(_cli, _userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            on_cmd(payload)
        except Exception:
            pass

    cli.on_message = on_message
    cli.connect(broker, port, 60)
    cli.subscribe(topic, qos=0)
    cli.loop_start()

    try:
        while not stop_event.is_set():
            stop_event.wait(0.2)
    finally:
        try:
            cli.loop_stop()
            cli.disconnect()
        except Exception:
            pass