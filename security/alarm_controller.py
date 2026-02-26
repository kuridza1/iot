# security/alarm_controller.py
import threading
from typing import Optional, Callable

from security.alarm_state import AlarmState
from security.door_held_state import DoorHeldState


class AlarmController:
    def __init__(
        self,
        buzzer,
        emit,
        pin: str,
        exit_delay_sec: float = 10.0,
        entry_delay_sec: float = 10.0,
        close_doors_cb: Optional[Callable[[], None]] = None,  # <-- NEW
    ):
        self.buzzer = buzzer
        self.emit = emit
        self.PIN = str(pin).strip()

        self.exit_delay_sec = float(exit_delay_sec)
        self.entry_delay_sec = float(entry_delay_sec)

        self.close_doors_cb = close_doors_cb  # <-- NEW

        self.state: AlarmState = AlarmState.DISARMED

        self._state_lock = threading.Lock()
        self._timer_lock = threading.Lock()

        self._exit_timer: Optional[threading.Timer] = None
        self._entry_timer: Optional[threading.Timer] = None

        self.ds1_held = DoorHeldState()

    # ----------------- helpers -----------------

    def _set_state(self, new_state: AlarmState, reason: Optional[str] = None) -> None:
        with self._state_lock:
            if self.state == new_state:
                return
            self.state = new_state

        self.emit("security", "ALARM_STATE", new_state.value, None, True)
        if reason:
            self.emit("security", "ALARM_REASON", reason, None, True)

    def _cancel_timers(self) -> None:
        with self._timer_lock:
            if self._exit_timer:
                self._exit_timer.cancel()
                self._exit_timer = None
            if self._entry_timer:
                self._entry_timer.cancel()
                self._entry_timer = None

    def _buzzer_on(self) -> None:
        if not self.buzzer.isOn():
            self.buzzer.on()
            self.emit("actuator", "DB", True, None, True)

    def _buzzer_off(self) -> None:
        if self.buzzer.isOn():
            self.buzzer.off()
            self.emit("actuator", "DB", False, None, True)

    # ----------------- public API -----------------

    def arm_begin(self, reason: str = "ARM_BY_PIN") -> None:
        with self._state_lock:
            st = self.state
        if st != AlarmState.DISARMED:
            self.emit("security", "ARM_IGNORED", st.value, None, True)
            return

        self._cancel_timers()
        self._set_state(AlarmState.EXIT_DELAY, reason)

        def _finish_exit_delay():
            with self._state_lock:
                if self.state != AlarmState.EXIT_DELAY:
                    return
            self._set_state(AlarmState.ARMED, "EXIT_DELAY_FINISHED")

        with self._timer_lock:
            self._exit_timer = threading.Timer(self.exit_delay_sec, _finish_exit_delay)
            self._exit_timer.daemon = True
            self._exit_timer.start()

    def disarm(self, reason: str = "DISARM") -> None:
        self._cancel_timers()
        self.ds1_held = DoorHeldState()
        self._buzzer_off()
        self._set_state(AlarmState.DISARMED, reason)

    def alarm_on(self, reason: str = "ALARM") -> None:
        self._cancel_timers()
        self._set_state(AlarmState.ALARM, reason)
        self._buzzer_on()

    def submit_pin(self, candidate: str, source: str = "PIN") -> None:
        cand = (candidate or "").strip()
        self.emit("security", "PIN_SUBMIT", source, None, True)

        if len(cand) != 4 or not cand.isdigit():
            self.emit("security", "PIN_FORMAT_INVALID", True, None, True)
            return

        if cand != self.PIN:
            self.emit("security", "PIN_FAIL", True, None, True)
            return

        self.emit("security", "PIN_OK", True, None, True)

        with self._state_lock:
            st = self.state

        # DISARMED + correct pin => ARM REQUEST
        if st == AlarmState.DISARMED:
            self.arm_begin("PIN_ARM_REQUEST")
            return

        # Any other state + correct pin => DISARM and (optionally) force-close doors
        self.disarm("PIN_DISARM")

        if self.close_doors_cb is not None:
            try:
                self.close_doors_cb()
            except Exception as e:
                # don't crash alarm logic if simulation close fails
                self.emit("security", "CLOSE_DOORS_FAILED", str(e), None, True)

    def on_door_event(self, door_code: str = "DS1", reason: str = "DOOR_EVENT") -> None:
        with self._state_lock:
            st = self.state

        if st == AlarmState.EXIT_DELAY:
            self.emit("security", "DOOR_IGNORED", f"{door_code}@EXIT_DELAY", None, True)
            return

        if st != AlarmState.ARMED:
            return

        self._set_state(AlarmState.ENTRY_DELAY, f"{reason}:{door_code}")

        def _entry_expire():
            with self._state_lock:
                if self.state != AlarmState.ENTRY_DELAY:
                    return
            self.alarm_on("ENTRY_DELAY_EXPIRED")

        with self._timer_lock:
            if self._entry_timer:
                self._entry_timer.cancel()
            self._entry_timer = threading.Timer(self.entry_delay_sec, _entry_expire)
            self._entry_timer.daemon = True
            self._entry_timer.start()

    # -------- DS1 held > N sec --------

    def handle_ds1_level(self, door_open: bool, now: float) -> None:
        if door_open:
            if not self.ds1_held.is_high:
                self.ds1_held.is_high = True
                self.ds1_held.high_since = now
                self.ds1_held.held_triggered = False
        else:
            self.ds1_held = DoorHeldState()

    def check_ds1_held(self, now: float, threshold_sec: float) -> None:
        h = self.ds1_held
        if h.is_high and h.high_since is not None and not h.held_triggered:
            if (now - h.high_since) >= float(threshold_sec):
                h.held_triggered = True
                self.emit("security", "DOOR_HELD", "DS1_HELD_5S", "event", True)
                self.alarm_on("DS1_HELD_5S")

    def trigger_alarm(self, reason: str = "INCIDENT", source: str = "REMOTE", meta: Optional[dict] = None) -> None:
        """
        Force ALARM state (e.g. GSG movement from PI2).
        If already alarming, do nothing.
        """
        with self._state_lock:
            if self.state == AlarmState.ALARM:
                return

        r = f"{source}:{reason}"
        if meta:
            try:
                self.emit("security", "INCIDENT_META", meta, None, True)
            except Exception:
                pass

        self.emit("security", "INCIDENT_ALARM_ON", r, None, True)
        self.alarm_on(r)

    def clear_alarm(self, reason: str = "CLEAR", source: str = "REMOTE") -> None:
        """
        Clear alarm back to DISARMED.
        If you prefer ARMED instead, replace DISARMED with ARMED.
        """
        self.emit("security", "INCIDENT_ALARM_OFF", f"{source}:{reason}", None, True)
        self.disarm(f"{source}:{reason}")