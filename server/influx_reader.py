from __future__ import annotations

from typing import Optional
from influxdb_client import InfluxDBClient


class InfluxReader:
    """@brief Reads latest telemetry values from InfluxDB (measurement: telemetry)."""

    def __init__(self, url: str, token: str, org: str, bucket: str) -> None:
        self._client = InfluxDBClient(url=url, token=token, org=org)
        self._org = org
        self._bucket = bucket
        self._query = self._client.query_api()

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    def latest_num(self, device: str, code: str, lookback: str = "15m") -> Optional[float]:
        flux = f"""
            from(bucket: "{self._bucket}")
            |> range(start: -{lookback})
            |> filter(fn: (r) =>
                r._measurement == "telemetry" and
                r.device == "{device}" and
                r.code == "{code}" and
                r._field == "value_num"
            )
            |> last()
            """
        tables = self._query.query(flux, org=self._org)
        for table in tables:
            for record in table.records:
                v = record.get_value()
                if v is not None:
                    return float(v)
        return None
