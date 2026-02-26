from typing import Any, Dict, Tuple

def load_alarm_pin(cfg: Dict[str, Any]) -> str:
    return str(
        cfg.get("ALARM", {}).get(
            "pin",
            cfg.get("pin", {}).get("value", "1234"),
        )
    ).strip()

def load_alarm_params(cfg: Dict[str, Any]) -> Tuple[float, float, float]:
    exit_delay = float(cfg.get("ALARM", {}).get("exit_delay_sec", 10.0))
    entry_delay = float(cfg.get("ALARM", {}).get("entry_delay_sec", cfg.get("alarm", {}).get("entry_delay_sec", 10.0)))
    door_held = float(cfg.get("ALARM", {}).get("door_held_sec", 5.0))
    return exit_delay, entry_delay, door_held