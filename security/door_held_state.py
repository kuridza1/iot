
from dataclasses import dataclass
from typing import Optional


@dataclass
class DoorHeldState:
    is_high: bool = False
    high_since: Optional[float] = None
    held_triggered: bool = False
