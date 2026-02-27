from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import time

from influx_writer import InfluxWriter
from mqtt_commands import MqttCommandPublisher


@dataclass
class AlarmState:
    alarm_active: bool = False
    alarm_reason: Optional[str] = None
    alarm_ts: float = 0.0

    people_inside: int = 0

    # PI-side state machine (ALARM_STATE)
    system_state: Optional[str] = None
    system_ts: float = 0.0

    # PI-side buzzer actuator state (DB)
    db_on: Optional[bool] = None
    db_ts: float = 0.0


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

    def snapshot(self, device: str) -> Dict[str, Any]:
        st = self._get(device)
        return {
            "device": device,
            "alarm_active": bool(st.alarm_active),
            "alarm_reason": st.alarm_reason,
            "alarm_ts": st.alarm_ts,
            "people_inside": int(st.people_inside),
            "system_state": st.system_state,
            "system_ts": st.system_ts,
            "db_on": st.db_on,
            "db_ts": st.db_ts,
            "actuators": {
                "DL": bool(getattr(st, "dl_on", False)),
            },
        }

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
        if st.alarm_active == bool(active) and (reason is None or reason == st.alarm_reason):
            return

        st.alarm_active = bool(active)
        st.alarm_reason = str(reason) if reason else None
        st.alarm_ts = time.time()

        # pošalji PI-u komandu (npr. da upali/gasi buzzer ili svoj alarm flow)
        self._cmd.publish_alarm(device, active, reason=reason)

        # upiši u Influx
        self._write_alarm_event(device, device_name, active, reason=reason)

    def on_event(self, payload: Dict[str, Any]) -> None:
        device = str(payload.get("device", "unknown"))
        device_name = str(payload.get("device_name", "unknown"))
        code = str(payload.get("code", ""))
        value = payload.get("value", None)

        st = self._get(device)
        now = time.time()

        # cache za UI
        if code == "PEOPLE_INSIDE":
            try:
                st.people_inside = int(float(value))
            except Exception:
                pass
            return

        if code == "ALARM_STATE":
            st.system_state = str(value)
            st.system_ts = now
            return

        if code == "DB":
            st.db_on = bool(value)
            st.db_ts = now
            return

        # logika: PIR pali alarm samo kad je prazno
        if code in ("DPIR1", "DPIR2", "DPIR3"):
            motion = bool(value)
            if motion and (st.people_inside <= 0) and (not st.alarm_active):
                self.set_alarm(device, device_name, True, reason="MOTION_WHEN_EMPTY")
            return

        # DMS_PIN varijanta (ako ti PI šalje baš DMS_PIN sa celim pin-om)
        if code == "DMS_PIN":
            if st.alarm_active and str(value) == self._alarm_pin:
                self.set_alarm(device, device_name, False, reason="PIN_OK")
            return

    def submit_pin(self, device: str, device_name: str, pin: str, source: str = "FE") -> bool:
        ok = str(pin) == self._alarm_pin
        if ok:
            # po specifikaciji: unosom PIN-a alarm se isključuje
            if self._get(device).alarm_active:
                self.set_alarm(device, device_name, False, reason=f"PIN_OK:{source}")
        return ok