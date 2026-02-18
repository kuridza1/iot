from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any
import time

from influx_writer import InfluxWriter
from mqtt_commands import MqttCommandPublisher


@dataclass
class AlarmState:
    alarm_active: bool = False
    people_inside: int = 0


class AlarmService:
    def __init__(self, influx: InfluxWriter, cmd: MqttCommandPublisher, alarm_pin: str) -> None:
        self._influx = influx
        self._cmd = cmd
        self._alarm_pin = str(alarm_pin)
        self._state: Dict[str, AlarmState] = {}

    def _get(self, device: str) -> AlarmState:
        if device not in self._state:
            self._state[device] = AlarmState()
        return self._state[device]

    def _write_alarm_event(self, device: str, device_name: str, active: bool, reason: str | None = None) -> None:
        ts = time.time()
        self._influx.write_event({
            "device": device,
            "device_name": device_name,
            "kind": "sensor",
            "code": "ALARM",
            "value": bool(active),
            "unit": None,
            "simulated": False,
            "ts": ts,
        })
        if reason:
            self._influx.write_event({
                "device": device,
                "device_name": device_name,
                "kind": "sensor",
                "code": "ALARM_REASON",
                "value": str(reason),
                "unit": None,
                "simulated": False,
                "ts": ts,
            })

    def set_alarm(self, device: str, device_name: str, active: bool, reason: str | None = None) -> None:
        st = self._get(device)
        if st.alarm_active == active:
            return
        st.alarm_active = active

        self._cmd.publish_alarm(device, active, reason=reason)

        self._write_alarm_event(device, device_name, active, reason=reason)

    def on_event(self, payload: Dict[str, Any]) -> None:
        device = str(payload.get("device", "unknown"))
        device_name = str(payload.get("device_name", "unknown"))
        code = str(payload.get("code", ""))
        value = payload.get("value", None)

        st = self._get(device)

        # Ako PI šalje PEOPLE_INSIDE, server ga samo pamti
        if code == "PEOPLE_INSIDE":
            try:
                st.people_inside = int(float(value))
            except Exception:
                pass
            return

        # PIR okidanje: pali alarm samo kad je prazno
        # (DPIR1/DPIR2 su bool)
        if code in ("DPIR1", "DPIR2", "DPIR3"):
            motion = bool(value)
            if motion and (st.people_inside <= 0) and (not st.alarm_active):
                self.set_alarm(device, device_name, True, reason="MOTION_WHEN_EMPTY")
            return

        # PIN unos: ako alarm aktivan i pin tačan => gasi
        if code == "DMS_PIN":
            if st.alarm_active and str(value) == self._alarm_pin:
                self.set_alarm(device, device_name, False, reason="PIN_OK")
            return
