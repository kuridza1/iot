import threading
from typing import Optional, Callable

from helper.telemetry import TelemetryEvent, now_ts

def make_emitter(publisher, device: str, device_name: str, ts_str: Callable[[], str]):
    io_lock = threading.Lock()
    suppress_console = {"value": False}  # mutable flag

    def safe_print(msg: str) -> None:
        with io_lock:
            print(msg)

    def set_suppress(flag: bool) -> None:
        suppress_console["value"] = flag

    def emit(kind: str, code: str, value, unit: Optional[str], simulated: bool) -> None:
        ev = TelemetryEvent(
            device=device,
            device_name=device_name,
            kind=kind,
            code=code,
            value=value,
            unit=unit,
            simulated=simulated,
            ts=now_ts(),
        )
        publisher.enqueue(ev)
        if not suppress_console["value"]:
            safe_print(f"[{ts_str()}] {code}: {value}")

    return emit, safe_print, set_suppress