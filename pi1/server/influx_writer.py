from __future__ import annotations

from typing import Any, Dict, Optional

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS


class InfluxWriter:
    """@brief Writes TelemetryEvent JSON payloads into InfluxDB."""

    def __init__(self, url: str, token: str, org: str, bucket: str) -> None:
        self._client = InfluxDBClient(url=url, token=token, org=org)
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        self._org = org
        self._bucket = bucket

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    def write_event(self, payload: Dict[str, Any]) -> None:
        # payload is TelemetryEvent.to_payload()
        device = str(payload.get("device", "unknown"))
        device_name = str(payload.get("device_name", "unknown"))
        kind = str(payload.get("kind", "unknown"))          # sensor/actuator
        code = str(payload.get("code", "unknown"))          # DUS1/DS1/DL...
        simulated = bool(payload.get("simulated", True))
        unit = payload.get("unit", None)
        ts = float(payload.get("ts", 0.0))

        value = payload.get("value", None)

        p = (
            Point("telemetry")
            .tag("device", device)
            .tag("device_name", device_name)
            .tag("kind", kind)
            .tag("code", code)
            .tag("simulated", str(simulated).lower())
        )

        if unit is not None:
            p = p.tag("unit", str(unit))

        # Influx fields must be scalar
        if isinstance(value, bool):
            p = p.field("value_bool", value)
            p = p.field("value_num", 1.0 if value else 0.0)
        elif isinstance(value, (int, float)):
            p = p.field("value_num", float(value))
        else:
            p = p.field("value_str", str(value))


        # timestamp in seconds → convert to ns precision
        p = p.time(int(ts * 1_000_000_000), WritePrecision.NS)

        self._write_api.write(bucket=self._bucket, org=self._org, record=p)
