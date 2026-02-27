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
    """
    Alarm logic (server-side) based on incoming telemetry payloads.

    Supported incoming codes (payload["code"]):
      - PEOPLE_INSIDE: numeric (int)
      - DPIR1/DPIR2/DPIR3: bool (motion)
      - DS1/DS2: bool (door state)
      - DMS_PIN: string PIN (disarm / stop alarm / cancel entry delay)
      - DMS_ARM_PIN: string PIN (request arming; arms after 10s)

    Emitted to Influx:
      - ALARM (bool) + optional ALARM_REASON (string)
      - ARMED (bool) + optional ARMED_REASON (string)
      - ENTRY_DELAY (bool) events when entry window starts/ends (optional)
    """

    # timings (seconds)
    ARMING_DELAY_SEC = 10.0
    DS_UNLOCKED_HOLD_SEC = 5.0
    ENTRY_DELAY_SEC = 10.0  # choose a value; spec doesn't define exact duration

    def __init__(self, influx: InfluxWriter, cmd: MqttCommandPublisher, alarm_pin: str) -> None:
        self._influx = influx
        self._cmd = cmd
        self._alarm_pin = str(alarm_pin)
        self._state: Dict[str, AlarmState] = {}

    # ----------------------------
    # State helpers
    # ----------------------------
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

    def _write_armed_event(self, device: str, device_name: str, armed: bool, reason: str | None = None) -> None:
        ts = time.time()
        self._influx.write_event({
            "device": device,
            "device_name": device_name,
            "kind": "sensor",
            "code": "ARMED",
            "value": bool(armed),
            "unit": None,
            "simulated": False,
            "ts": ts,
        })
        if reason:
            self._influx.write_event({
                "device": device,
                "device_name": device_name,
                "kind": "sensor",
                "code": "ARMED_REASON",
                "value": str(reason),
                "unit": None,
                "simulated": False,
                "ts": ts,
            })

    def _write_entry_delay_event(self, device: str, device_name: str, active: bool) -> None:
        ts = time.time()
        self._influx.write_event({
            "device": device,
            "device_name": device_name,
            "kind": "sensor",
            "code": "ENTRY_DELAY",
            "value": bool(active),
            "unit": None,
            "simulated": False,
            "ts": ts,
        })

    # ----------------------------
    # Public control methods
    # ----------------------------
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

    def set_armed(self, device: str, device_name: str, armed: bool, reason: str | None = None) -> None:
        st = self._get(device)
        if st.armed == armed and st.arming_until_ts is None:
            return

        st.armed = armed
        st.arming_until_ts = None
        st.entry_until_ts = None

        self._write_armed_event(device, device_name, armed, reason=reason)

        # optional: inform PI (if you have such command)
        # self._cmd.publish_armed(device, armed, reason=reason)

    def request_arm(self, device: str, device_name: str) -> None:
        st = self._get(device)
        now = time.time()
        st.arming_until_ts = now + self.ARMING_DELAY_SEC
        self._write_armed_event(device, device_name, False, reason="ARMING_10S")

    def disarm_and_clear(self, device: str, device_name: str, reason: str) -> None:
        st = self._get(device)
        st.entry_until_ts = None
        st.arming_until_ts = None

        if st.alarm_active:
            self.set_alarm(device, device_name, False, reason=reason)

        if st.armed:
            self.set_armed(device, device_name, False, reason=reason)
        else:
            # still write a disarm event if you want visibility; optional
            pass

    # ----------------------------
    # Internal ticking (time-based transitions)
    # ----------------------------
    def _tick(self, device: str, device_name: str, st: AlarmState) -> None:
        now = time.time()

        # Finish arming after delay
        if st.arming_until_ts is not None and now >= st.arming_until_ts:
            st.arming_until_ts = None
            if not st.armed:
                st.armed = True
                self._write_armed_event(device, device_name, True, reason="ARMED_AFTER_10S")

        # Entry delay expired -> alarm (only if armed and not already alarming)
        if st.entry_until_ts is not None and now >= st.entry_until_ts:
            st.entry_until_ts = None
            self._write_entry_delay_event(device, device_name, False)
            if st.armed and not st.alarm_active:
                self.set_alarm(device, device_name, True, reason="ENTRY_TIMEOUT")

    # ----------------------------
    # Main ingestion hook
    # ----------------------------
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
