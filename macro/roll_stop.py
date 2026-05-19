"""Roll-until-warning then tail-roll stop logic."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RollStopTracker:
    """After footer parses ``rolls_left == threshold``, roll ``tail_count`` more times."""

    threshold: int = 2
    tail_count: int = 2
    tail_remaining: int | None = None
    saw_warning: bool = False

    def on_roll_parsed(self, rolls_left: int | None) -> bool:
        """
        Update state from a roll embed's ``rolls_left`` field.

        Returns True when the macro should stop after this roll (and its post-roll).
        """
        if (
            rolls_left is not None
            and int(rolls_left) == self.threshold
            and self.tail_remaining is None
        ):
            self.saw_warning = True
            self.tail_remaining = self.tail_count
            return False

        if self.tail_remaining is not None:
            self.tail_remaining -= 1
            return self.tail_remaining <= 0

        return False

    def should_stop_before_roll(self, rolls_left: int | None) -> bool:
        """Only stop early when completely out of rolls (not at warning threshold)."""
        return rolls_left is not None and int(rolls_left) <= 0
