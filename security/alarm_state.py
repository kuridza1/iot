from enum import Enum


class AlarmState(str, Enum):
    DISARMED = "DISARMED"
    EXIT_DELAY = "EXIT_DELAY"
    ARMED = "ARMED"
    ENTRY_DELAY = "ENTRY_DELAY"
    ALARM = "ALARM"
