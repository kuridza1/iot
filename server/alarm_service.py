from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
import time


@dataclass
class AlarmState:
    # cached for UI
    people_inside: int = 0

    # emitted by PI (AlarmController)
    system_state: Optional[str] = None      # ALARM_STATE
    system_ts: float = 0.0

    alarm_reason: Optional[str] = None      # ALARM_REASON (string)
    alarm_reason_ts: float = 0.0

    db_on: Optional[bool] = None            # actuator DB
    db_ts: float = 0.0

    dl_on: Optional[bool] = None            # actuator DL (if you emit it)
    dl_ts: float = 0.0

    last_ts: float = 0.0


class AlarmService:
    """
    Passive cache only.

    - NO alarm logic
    - NO pin validation
    - NO MQTT commands
    - NO writing additional ALARM/ARMED events

    The PI devices are the source of truth and emit:
      - ALARM_STATE, ALARM_REASON
      - DB / DL actuator telemetry
      - PEOPLE_INSIDE telemetry
    """

    def __init__(self) -> None:
        self._state: Dict[str, AlarmState] = {}

    def _get(self, device: str) -> AlarmState:
        d = str(device).strip() or "unknown"
        if d not in self._state:
            self._state[d] = AlarmState()
        return self._state[d]

    def snapshot(self, device: str) -> Dict[str, Any]:
        d = str(device).strip() or "unknown"
        st = self._get(d)

        return {
            "device": d,
            "people_inside": int(st.people_inside),

            "system_state": st.system_state,
            "system_ts": st.system_ts,

            "alarm_reason": st.alarm_reason,
            "alarm_reason_ts": st.alarm_reason_ts,

            "db_on": st.db_on,
            "db_ts": st.db_ts,

            "actuators": {
                "DL": st.dl_on,
            },
            "dl_ts": st.dl_ts,

            "last_ts": st.last_ts,
        }

    def on_event(self, payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return

        device = str(payload.get("device", "unknown")).strip() or "unknown"
        code = str(payload.get("code", "")).strip()
        value = payload.get("value", None)

        st = self._get(device)
        now = time.time()
        st.last_ts = now

        if code == "PEOPLE_INSIDE":
            try:
                st.people_inside = int(float(value))
            except Exception:
                pass
            return

        if code == "ALARM_STATE":
            st.system_state = str(value) if value is not None else None
            st.system_ts = now
            return

        if code == "ALARM_REASON":
            st.alarm_reason = str(value) if value is not None else None
            st.alarm_reason_ts = now
            return

        if code == "DB":
            st.db_on = bool(value)
            st.db_ts = now
            return

        if code == "DL":
            st.dl_on = bool(value)
            st.dl_ts = now
            return