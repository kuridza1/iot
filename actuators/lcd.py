from dataclasses import dataclass


@dataclass
class Lcd:
    """@brief LCD abstraction (simulated). Real HW can be added later."""
    simulated: bool = True

    def __post_init__(self) -> None:
        self._text = ""

    def show(self, text: str) -> None:
        self._text = str(text)
        # simulated: just keep state (and main prints it)

    def last_text(self) -> str:
        return self._text
