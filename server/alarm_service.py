from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import time

from influx_writer import InfluxWriter
from mqtt_commands import MqttCommandPublisher


@dataclass
class AlarmState:
    alarm_active: bool = False
    people_inside: int = 0

    # Security system mode
    armed: bool = False                  # system active (armed)
    arming_until_ts: Optional[float] = None  # when arming completes (10s delay)
    entry_until_ts: Optional[float] = None   # deadline to enter PIN after door event

    # DS hold detection: DS1/DS2 stays ON longer than 5s => alarm until DS changes
    ds_on_since: Dict[str, float] = field(default_factory=dict)

    # Track last alarm reason (optional, helps selective auto-clear)
    last_alarm_reason: Optional[str] = None


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

    # ----------------------------
    # Influx writes
    # ----------------------------
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
        if st.alarm_active == active:
            return

        st.alarm_active = active
        st.last_alarm_reason = reason

        # MQTT command (for DB / buzzer / whatever PI should do)
        self._cmd.publish_alarm(device, active, reason=reason)

        # Persist + Grafana
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

        # apply time-based transitions on every incoming event
        self._tick(device, device_name, st)

        # ----------------------------
        # People count (server caches)
        # ----------------------------
        if code == "PEOPLE_INSIDE":
            try:
                st.people_inside = int(float(value))
            except Exception:
                pass
            return

        # ----------------------------
        # Arm request from DMS
        # ----------------------------
        if code == "DMS_ARM_PIN":
            if str(value) == self._alarm_pin and not st.armed:
                self.request_arm(device, device_name)
            return

        # ----------------------------
        # PIN entered: disarm + clear alarm + stop entry delay
        # ----------------------------
        if code == "DMS_PIN":
            if str(value) == self._alarm_pin:
                # spec: PIN disables alarm and deactivates system
                self.disarm_and_clear(device, device_name, reason="PIN_OK")
            return

        # ----------------------------
        # PIR motion: alarm only when empty (per your current rule)
        # ----------------------------
        if code in ("DPIR1", "DPIR2", "DPIR3"):
            motion = bool(value)
            if motion and (st.people_inside <= 0) and (not st.alarm_active):
                self.set_alarm(device, device_name, True, reason="MOTION_WHEN_EMPTY")
            return

        # ----------------------------
        # Door sensors: DS1/DS2 logic
        # - DS on >5s => ALARM until DS changes (state flips)
        # - If armed and DS triggers => start entry delay; if PIN not entered => alarm on timeout
        # ----------------------------
        if code in ("DS1", "DS2"):
            is_on = bool(value)
            now = time.time()

            if is_on:
                # start / keep hold timer
                if code not in st.ds_on_since:
                    st.ds_on_since[code] = now

                # armed -> start entry delay window if not already started
                if st.armed and not st.alarm_active and st.entry_until_ts is None:
                    st.entry_until_ts = now + self.ENTRY_DELAY_SEC
                    self._write_entry_delay_event(device, device_name, True)

                # if held ON long enough -> alarm until it changes
                started = st.ds_on_since.get(code)
                if started is not None and (now - started) >= self.DS_UNLOCKED_HOLD_SEC:
                    if not st.alarm_active:
                        self.set_alarm(device, device_name, True, reason=f"UNLOCKED_{code}_GT_5S")

            else:
                # DS changed back -> clear hold timer
                st.ds_on_since.pop(code, None)

                # If alarm was caused by unlocked door hold, you can auto-clear when door changes.
                # Spec: "ALARM dok se stanje DS-a ne promeni" -> on change, turn off.
                if st.alarm_active and (st.last_alarm_reason or "").startswith("UNLOCKED_"):
                    self.set_alarm(device, device_name, False, reason=f"{code}_CHANGED")

                # Also end entry delay if door returned to normal (optional; you may keep it running)
                if st.entry_until_ts is not None:
                    st.entry_until_ts = None
                    self._write_entry_delay_event(device, device_name, False)

            return

        # Any other codes: ignore
        return