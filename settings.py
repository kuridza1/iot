import json
from pathlib import Path
from typing import Any, Dict

def load_settings(path: str = "settings.json") -> Dict[str, Any]:
    """@brief Load settings from JSON file."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)
