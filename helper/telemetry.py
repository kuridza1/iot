from __future__ import annotations

from dataclasses import dataclass, asdict
import time
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TelemetryEvent:
    """@brief One sensor/actuator event ready for MQTT/Influx."""
    device: str            # "PI1"
    device_name: str       # "SmartDoor"
    kind: str              # "sensor" or "actuator"
    code: str              # "DUS1", "DS1", "DL", ...
    value: Any             # float/bool/int/str
    unit: Optional[str]    # "cm", None, ...
    simulated: bool
    ts: float              # epoch seconds

    def to_payload(self) -> Dict[str, Any]:
        return asdict(self)

    def default_topic(self, topic_prefix: str) -> str:
        return f"{topic_prefix}/{self.device}/{self.kind}/{self.code}"


def now_ts() -> float:
    return time.time()
